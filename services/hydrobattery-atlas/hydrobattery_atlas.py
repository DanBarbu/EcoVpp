"""ECO-VPP Hydrobattery Atlas.

A catalogue of pumped-hydro energy-storage sites ("hydrobatteries") the VPP can
dispatch as long-duration flexibility. Each site stores its physical
characteristics (hydraulic head, usable reservoir volume, rated turbine/pump
power, round-trip efficiency) and a live state-of-charge. The service derives
the usable energy capacity from first principles and exposes dispatch-feasibility
and fleet-summary endpoints consumed by the operator dashboard / map view.

Stored energy of a pumped-hydro reservoir:

    E = rho * g * V * h * eta            [joules]
    E_kWh = E / 3.6e6

with rho = 1000 kg/m^3 (water) and g = 9.81 m/s^2. The round-trip efficiency
``eta`` is applied as the deliverable-energy factor so the reported capacity is
the energy the fleet can actually return to the grid.
"""
from __future__ import annotations

import hmac
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from uuid import UUID, uuid4

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from pydantic import BaseModel, Field, field_validator
from starlette.responses import Response

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("hydrobattery-atlas")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://eco:eco@postgres:5432/ecovpp",
)
ECOVPP_ENV = os.getenv("ECOVPP_ENV", "dev")
INGEST_TOKEN = os.getenv("INGEST_TOKEN", "dev-token")

# Fail closed: outside dev, refuse to start with a missing/placeholder token so
# a forgeable default can never reach production.
_WEAK_TOKENS = {"", "dev-token", "change-me"}
if ECOVPP_ENV != "dev" and INGEST_TOKEN in _WEAK_TOKENS:
    raise RuntimeError(
        "INGEST_TOKEN is unset or a placeholder while ECOVPP_ENV != 'dev'. "
        "Set a strong INGEST_TOKEN (e.g. from the eco-vpp-secrets Secret)."
    )

# Cross-origin: restrict to the dashboard origin(s) in prod; '*' only in dev.
CORS_ORIGINS = [o for o in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if o] or (
    ["*"] if ECOVPP_ENV == "dev" else []
)

WATER_DENSITY_KG_M3 = 1000.0
GRAVITY_M_S2 = 9.81
J_PER_KWH = 3_600_000.0

STATUSES = {"planned", "construction", "operational", "decommissioned"}

REGISTERED = Counter(
    "ecovpp_hydrobattery_registered_total",
    "Hydrobattery sites registered",
)
FLEET_STORAGE_KWH = Gauge(
    "ecovpp_hydrobattery_fleet_storage_kwh",
    "Sum of deliverable storage capacity across operational hydrobatteries",
)


def storage_capacity_kwh(
    head_m: float, usable_volume_m3: float, round_trip_efficiency: float
) -> float:
    """Deliverable energy capacity of a pumped-hydro reservoir, in kWh."""
    if head_m <= 0 or usable_volume_m3 <= 0:
        return 0.0
    joules = (
        WATER_DENSITY_KG_M3
        * GRAVITY_M_S2
        * usable_volume_m3
        * head_m
        * round_trip_efficiency
    )
    return joules / J_PER_KWH


def dispatch_plan(
    *,
    rated_power_kw: float,
    storage_kwh: float,
    state_of_charge: float,
    power_kw: float,
    hours: float,
) -> dict[str, Any]:
    """Feasibility of discharging ``power_kw`` for ``hours`` from one site.

    Returns the requested energy, what's available at the current state of
    charge, whether the request is feasible, and the limiting factor.
    """
    available_kwh = storage_kwh * state_of_charge
    requested_kwh = power_kw * hours
    power_ok = power_kw <= rated_power_kw
    energy_ok = requested_kwh <= available_kwh

    if not power_ok and not energy_ok:
        limiting = "power_and_energy"
    elif not power_ok:
        limiting = "power"
    elif not energy_ok:
        limiting = "energy"
    else:
        limiting = None

    deliverable_power_kw = min(power_kw, rated_power_kw)
    max_hours_at_power = (
        available_kwh / deliverable_power_kw if deliverable_power_kw > 0 else 0.0
    )
    return {
        "feasible": power_ok and energy_ok,
        "limiting_factor": limiting,
        "requested_kwh": round(requested_kwh, 4),
        "available_kwh": round(available_kwh, 4),
        "deliverable_power_kw": round(deliverable_power_kw, 4),
        "max_hours_at_power": round(max_hours_at_power, 4),
    }


class HydrobatteryIn(BaseModel):
    name: str = Field(..., min_length=1)
    did: str | None = Field(default=None, description="Optional VPP asset DID")
    status: str = Field(default="operational")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    head_m: float = Field(..., gt=0.0, description="Hydraulic head in metres")
    usable_volume_m3: float = Field(..., gt=0.0, description="Usable reservoir volume")
    rated_power_kw: float = Field(..., gt=0.0)
    round_trip_efficiency: float = Field(default=0.80, gt=0.0, le=1.0)
    state_of_charge: float = Field(default=0.5, ge=0.0, le=1.0)
    storage_capacity_kwh: float | None = Field(
        default=None,
        description="Override the derived capacity; computed from head+volume when omitted",
    )

    @field_validator("status")
    @classmethod
    def status_known(cls, v: str) -> str:
        if v not in STATUSES:
            raise ValueError(f"status must be one of {sorted(STATUSES)}")
        return v

    @field_validator("name", "did")
    @classmethod
    def strip_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("must not be blank")
        return v

    def resolved_capacity_kwh(self) -> float:
        if self.storage_capacity_kwh is not None:
            return self.storage_capacity_kwh
        return storage_capacity_kwh(
            self.head_m, self.usable_volume_m3, self.round_trip_efficiency
        )


class SocUpdate(BaseModel):
    state_of_charge: float = Field(..., ge=0.0, le=1.0)


SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS hydrobatteries (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    did TEXT UNIQUE,
    status TEXT NOT NULL DEFAULT 'operational',
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    head_m DOUBLE PRECISION NOT NULL,
    usable_volume_m3 DOUBLE PRECISION NOT NULL,
    rated_power_kw DOUBLE PRECISION NOT NULL,
    storage_capacity_kwh DOUBLE PRECISION NOT NULL,
    round_trip_efficiency DOUBLE PRECISION NOT NULL DEFAULT 0.80,
    state_of_charge DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS hydrobatteries_status_idx ON hydrobatteries (status);
CREATE INDEX IF NOT EXISTS hydrobatteries_geo_idx ON hydrobatteries (latitude, longitude);
"""


async def _refresh_fleet_gauge(conn: asyncpg.Connection) -> None:
    total = await conn.fetchval(
        "SELECT COALESCE(SUM(storage_capacity_kwh * state_of_charge), 0) "
        "FROM hydrobatteries WHERE status = 'operational'"
    )
    FLEET_STORAGE_KWH.set(float(total or 0.0))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    app.state.pool = pool
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_DDL)
        await _refresh_fleet_gauge(conn)
    log.info("schema ready, db pool initialised")
    try:
        yield
    finally:
        await pool.close()


app = FastAPI(title="ECO-VPP Hydrobattery Atlas", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool


def require_token(request: Request) -> None:
    token = request.headers.get("x-ingest-token") or ""
    if not hmac.compare_digest(token, INGEST_TOKEN):
        raise HTTPException(status_code=401, detail="invalid ingest token")


def _row_to_site(r: asyncpg.Record) -> dict[str, Any]:
    site = dict(r)
    site["id"] = str(site["id"])
    cap = float(site["storage_capacity_kwh"])
    soc = float(site["state_of_charge"])
    site["available_energy_kwh"] = round(cap * soc, 4)
    site["chargeable_headroom_kwh"] = round(cap * (1.0 - soc), 4)
    return site


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/api/v1/hydrobatteries", status_code=201, dependencies=[Depends(require_token)])
async def register_site(
    site: HydrobatteryIn, pool: asyncpg.Pool = Depends(get_pool)
) -> dict[str, Any]:
    site_id = uuid4()
    capacity = site.resolved_capacity_kwh()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO hydrobatteries
                  (id, name, did, status, latitude, longitude, head_m,
                   usable_volume_m3, rated_power_kw, storage_capacity_kwh,
                   round_trip_efficiency, state_of_charge)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                RETURNING *
                """,
                site_id,
                site.name,
                site.did,
                site.status,
                site.latitude,
                site.longitude,
                site.head_m,
                site.usable_volume_m3,
                site.rated_power_kw,
                capacity,
                site.round_trip_efficiency,
                site.state_of_charge,
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(status_code=409, detail="DID already registered") from exc
        await _refresh_fleet_gauge(conn)
    REGISTERED.inc()
    return _row_to_site(row)


@app.get("/api/v1/hydrobatteries")
async def list_sites(
    pool: asyncpg.Pool = Depends(get_pool),
    status: str | None = Query(default=None),
    min_lat: float | None = Query(default=None, ge=-90.0, le=90.0),
    max_lat: float | None = Query(default=None, ge=-90.0, le=90.0),
    min_lon: float | None = Query(default=None, ge=-180.0, le=180.0),
    max_lon: float | None = Query(default=None, ge=-180.0, le=180.0),
) -> dict[str, list[dict[str, Any]]]:
    if status is not None and status not in STATUSES:
        raise HTTPException(status_code=422, detail=f"unknown status: {status}")
    clauses: list[str] = []
    args: list[Any] = []
    for value, sql in (
        (status, "status = {}"),
        (min_lat, "latitude >= {}"),
        (max_lat, "latitude <= {}"),
        (min_lon, "longitude >= {}"),
        (max_lon, "longitude <= {}"),
    ):
        if value is not None:
            args.append(value)
            clauses.append(sql.format(f"${len(args)}"))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT * FROM hydrobatteries {where} ORDER BY rated_power_kw DESC", *args
        )
    return {"hydrobatteries": [_row_to_site(r) for r in rows]}


@app.get("/api/v1/atlas/summary")
async def atlas_summary(pool: asyncpg.Pool = Depends(get_pool)) -> dict[str, Any]:
    """Fleet-wide aggregates + bounding box for the dashboard map view."""
    async with pool.acquire() as conn:
        agg = await conn.fetchrow(
            """
            SELECT
              COUNT(*)                                           AS sites,
              COALESCE(SUM(rated_power_kw), 0)                   AS total_rated_power_kw,
              COALESCE(SUM(storage_capacity_kwh), 0)            AS total_storage_kwh,
              COALESCE(SUM(storage_capacity_kwh * state_of_charge), 0) AS available_kwh,
              MIN(latitude) AS min_lat, MAX(latitude) AS max_lat,
              MIN(longitude) AS min_lon, MAX(longitude) AS max_lon
            FROM hydrobatteries
            WHERE status = 'operational'
            """
        )
        by_status = await conn.fetch(
            "SELECT status, COUNT(*) AS n FROM hydrobatteries GROUP BY status"
        )
    bbox = None
    if agg["sites"]:
        bbox = {
            "min_lat": agg["min_lat"],
            "max_lat": agg["max_lat"],
            "min_lon": agg["min_lon"],
            "max_lon": agg["max_lon"],
        }
    return {
        "operational_sites": agg["sites"],
        "total_rated_power_kw": round(float(agg["total_rated_power_kw"]), 4),
        "total_storage_kwh": round(float(agg["total_storage_kwh"]), 4),
        "available_kwh": round(float(agg["available_kwh"]), 4),
        "bounding_box": bbox,
        "by_status": {r["status"]: r["n"] for r in by_status},
    }


async def _fetch_site(conn: asyncpg.Connection, site_id: UUID) -> asyncpg.Record:
    row = await conn.fetchrow("SELECT * FROM hydrobatteries WHERE id = $1", site_id)
    if row is None:
        raise HTTPException(status_code=404, detail="hydrobattery not found")
    return row


@app.get("/api/v1/hydrobatteries/{site_id}")
async def get_site(site_id: UUID, pool: asyncpg.Pool = Depends(get_pool)) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await _fetch_site(conn, site_id)
    return _row_to_site(row)


@app.get("/api/v1/hydrobatteries/{site_id}/dispatch")
async def dispatch(
    site_id: UUID,
    power_kw: float = Query(..., gt=0.0),
    hours: float = Query(..., gt=0.0),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await _fetch_site(conn, site_id)
    plan = dispatch_plan(
        rated_power_kw=float(row["rated_power_kw"]),
        storage_kwh=float(row["storage_capacity_kwh"]),
        state_of_charge=float(row["state_of_charge"]),
        power_kw=power_kw,
        hours=hours,
    )
    return {"id": str(row["id"]), "name": row["name"], "request": {"power_kw": power_kw, "hours": hours}, **plan}


@app.patch("/api/v1/hydrobatteries/{site_id}/soc", dependencies=[Depends(require_token)])
async def update_soc(
    site_id: UUID, body: SocUpdate, pool: asyncpg.Pool = Depends(get_pool)
) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE hydrobatteries
            SET state_of_charge = $2, updated_at = $3
            WHERE id = $1
            RETURNING *
            """,
            site_id,
            body.state_of_charge,
            datetime.now(tz=timezone.utc),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="hydrobattery not found")
        await _refresh_fleet_gauge(conn)
    return _row_to_site(row)


@app.delete("/api/v1/hydrobatteries/{site_id}", status_code=204, dependencies=[Depends(require_token)])
async def delete_site(site_id: UUID, pool: asyncpg.Pool = Depends(get_pool)) -> Response:
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM hydrobatteries WHERE id = $1", site_id)
        await _refresh_fleet_gauge(conn)
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail="hydrobattery not found")
    return Response(status_code=204)
