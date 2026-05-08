"""ECO-VPP Webhook Receiver.

Ingests Mainflux MQTT bridge webhooks plus direct HaLow telemetry POSTs from
ESP32-S3 sub-EUR20 nodes, persists to PostgreSQL, and exposes summary endpoints
consumed by the React dashboard.
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator
from uuid import UUID, uuid4

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field, field_validator
from starlette.responses import Response

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("webhook-receiver")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://eco:eco@postgres:5432/ecovpp",
)
INGEST_TOKEN = os.getenv("INGEST_TOKEN", "dev-token")

INGEST_COUNTER = Counter(
    "ecovpp_telemetry_ingested_total",
    "Telemetry records persisted",
    ["source"],
)
INGEST_LATENCY = Histogram(
    "ecovpp_telemetry_ingest_seconds",
    "Time spent persisting one telemetry record",
)


class TelemetryIn(BaseModel):
    """Single telemetry sample.

    HaLow links can introduce >5s of latency, so the device timestamp is
    authoritative. The server timestamp is recorded separately for forensics.
    """

    did: str = Field(..., description="Decentralized Identifier of the source node")
    voltage: float | None = None
    current: float | None = None
    power_w: float | None = None
    energy_kwh: float | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    timestamp: datetime | None = None
    extra: dict[str, Any] | None = None

    @field_validator("did")
    @classmethod
    def did_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("did must not be empty")
        return v


class AssetIn(BaseModel):
    did: str
    asset_type: str = Field(..., pattern=r"^(meter|inverter|battery|ev|heater|load)$")
    location: str | None = None
    capacity_kw: float | None = None


class WebSocketHub:
    """Fan-out for flexibility-engine signals to dashboard clients."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        message = json.dumps(payload, default=str)
        dead: list[WebSocket] = []
        for ws in self._clients:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


hub = WebSocketHub()


SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS assets (
    id UUID PRIMARY KEY,
    did TEXT UNIQUE NOT NULL,
    asset_type TEXT NOT NULL,
    location TEXT,
    capacity_kw DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS telemetry (
    id BIGSERIAL PRIMARY KEY,
    did TEXT NOT NULL,
    voltage DOUBLE PRECISION,
    current DOUBLE PRECISION,
    power_w DOUBLE PRECISION,
    energy_kwh DOUBLE PRECISION,
    confidence DOUBLE PRECISION,
    device_ts TIMESTAMPTZ NOT NULL,
    server_ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    extra JSONB
);
CREATE INDEX IF NOT EXISTS telemetry_did_ts_idx ON telemetry (did, device_ts DESC);

CREATE TABLE IF NOT EXISTS energy_shares (
    id BIGSERIAL PRIMARY KEY,
    asset TEXT NOT NULL,
    kwh DOUBLE PRECISION NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    share_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    settled BOOLEAN NOT NULL DEFAULT false,
    settlement_tx TEXT
);
CREATE INDEX IF NOT EXISTS shares_time_idx ON energy_shares (share_time DESC);

CREATE TABLE IF NOT EXISTS verification_queue (
    id UUID PRIMARY KEY,
    did TEXT NOT NULL,
    payload JSONB NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    queued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved BOOLEAN NOT NULL DEFAULT false
);
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    app.state.pool = pool
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_DDL)
    log.info("schema ready, db pool initialised")
    try:
        yield
    finally:
        await pool.close()


app = FastAPI(title="ECO-VPP Webhook Receiver", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool


def require_token(request: Request) -> None:
    token = request.headers.get("x-ingest-token")
    if token != INGEST_TOKEN:
        raise HTTPException(status_code=401, detail="invalid ingest token")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/api/v1/assets", status_code=201)
async def register_asset(asset: AssetIn, pool: asyncpg.Pool = Depends(get_pool)) -> dict[str, Any]:
    asset_id = uuid4()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                """
                INSERT INTO assets (id, did, asset_type, location, capacity_kw)
                VALUES ($1, $2, $3, $4, $5)
                """,
                asset_id,
                asset.did,
                asset.asset_type,
                asset.location,
                asset.capacity_kw,
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(status_code=409, detail="DID already registered") from exc
    return {"id": str(asset_id), **asset.model_dump()}


@app.get("/api/v1/assets")
async def list_assets(pool: asyncpg.Pool = Depends(get_pool)) -> dict[str, list[dict[str, Any]]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, did, asset_type, location, capacity_kw FROM assets ORDER BY created_at DESC"
        )
    return {"assets": [dict(r) | {"id": str(r["id"])} for r in rows]}


@app.post("/api/v1/telemetry/ingest", status_code=202, dependencies=[Depends(require_token)])
async def ingest_telemetry(
    sample: TelemetryIn, pool: asyncpg.Pool = Depends(get_pool)
) -> dict[str, Any]:
    device_ts = sample.timestamp or datetime.now(tz=timezone.utc)
    with INGEST_LATENCY.time():
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO telemetry
                  (did, voltage, current, power_w, energy_kwh, confidence, device_ts, extra)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                sample.did,
                sample.voltage,
                sample.current,
                sample.power_w,
                sample.energy_kwh,
                sample.confidence,
                device_ts,
                json.dumps(sample.extra) if sample.extra else None,
            )
            if sample.confidence is not None and sample.confidence < 0.80:
                await conn.execute(
                    """
                    INSERT INTO verification_queue (id, did, payload, confidence)
                    VALUES ($1, $2, $3, $4)
                    """,
                    uuid4(),
                    sample.did,
                    json.dumps(sample.model_dump(mode="json")),
                    sample.confidence,
                )
    INGEST_COUNTER.labels(source="halow").inc()
    return {"status": "accepted", "did": sample.did, "device_ts": device_ts.isoformat()}


@app.post("/api/v1/mainflux/webhook", dependencies=[Depends(require_token)])
async def mainflux_webhook(request: Request, pool: asyncpg.Pool = Depends(get_pool)) -> dict[str, Any]:
    body = await request.json()
    messages = body if isinstance(body, list) else [body]
    persisted = 0
    async with pool.acquire() as conn:
        for msg in messages:
            try:
                payload = msg.get("payload") if isinstance(msg, dict) else None
                if isinstance(payload, str):
                    payload = json.loads(payload)
                payload = payload or msg
                sample = TelemetryIn(**payload)
            except Exception as exc:  # noqa: BLE001
                log.warning("dropping malformed message: %s", exc)
                continue
            device_ts = sample.timestamp or datetime.now(tz=timezone.utc)
            await conn.execute(
                """
                INSERT INTO telemetry
                  (did, voltage, current, power_w, energy_kwh, confidence, device_ts, extra)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                sample.did,
                sample.voltage,
                sample.current,
                sample.power_w,
                sample.energy_kwh,
                sample.confidence,
                device_ts,
                json.dumps(sample.extra) if sample.extra else None,
            )
            persisted += 1
    INGEST_COUNTER.labels(source="mainflux").inc(persisted)
    return {"persisted": persisted}


@app.get("/api/shares/latest")
async def latest_shares(pool: asyncpg.Pool = Depends(get_pool)) -> list[dict[str, Any]]:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT asset, kwh, price, share_time AS time, settled, settlement_tx
            FROM energy_shares
            WHERE share_time >= $1
            ORDER BY share_time DESC
            LIMIT 200
            """,
            cutoff,
        )
    return [dict(r) for r in rows]


@app.post("/api/shares")
async def create_share(
    asset: str,
    kwh: float,
    price: float,
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict[str, Any]:
    """Record a community-internal share (RED II Collective Self-Consumption)."""
    async with pool.acquire() as conn:
        share_id = await conn.fetchval(
            """
            INSERT INTO energy_shares (asset, kwh, price)
            VALUES ($1, $2, $3) RETURNING id
            """,
            asset,
            kwh,
            price,
        )
    return {"id": share_id, "asset": asset, "kwh": kwh, "price": price}


@app.post("/api/internal/incentive")
async def push_incentive(payload: dict[str, Any]) -> dict[str, Any]:
    """Internal hook: flexibility-engine pushes incentive updates here, we
    fan them out over WebSocket to dashboard clients."""
    await hub.broadcast(payload)
    return {"broadcasted": True}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()  # ignore client pings
    except WebSocketDisconnect:
        hub.disconnect(ws)
