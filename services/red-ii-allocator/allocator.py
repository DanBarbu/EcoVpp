"""RED II Collective Self-Consumption allocator.

Every cycle:
  1. Reads the last interval's PV production (sum of telemetry where asset
     type = inverter) and per-apartment consumption (asset type = meter).
  2. Allocates surplus solar pro-rata across consuming members.
  3. Writes the resulting allocations to `energy_shares` (priced at the
     internal sharing tariff, EUR/kWh) so the settlement service can anchor
     them on Energy Web Origin.

Surplus that exceeds aggregate demand is queued as a GSY-e P2P offer.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
import httpx

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("red-ii")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://eco:eco@postgres:5432/ecovpp")
INTERNAL_PRICE_EUR_KWH = float(os.getenv("INTERNAL_PRICE_EUR_KWH", "0.18"))
INTERVAL_MIN = int(os.getenv("ALLOCATION_INTERVAL_MIN", "15"))
GSY_URL = os.getenv("GSY_URL", "")
GSY_TOKEN = os.getenv("GSY_TOKEN", "")


async def gather_window(conn: asyncpg.Connection, end: datetime) -> tuple[float, list[tuple[str, float]]]:
    start = end - timedelta(minutes=INTERVAL_MIN)
    inverter_rows = await conn.fetch(
        """
        SELECT a.did, COALESCE(SUM(t.energy_kwh), 0) AS kwh
        FROM telemetry t
        JOIN assets a ON a.did = t.did
        WHERE a.asset_type = 'inverter'
          AND t.device_ts >= $1 AND t.device_ts < $2
        GROUP BY a.did
        """,
        start,
        end,
    )
    meter_rows = await conn.fetch(
        """
        SELECT a.did, COALESCE(SUM(t.energy_kwh), 0) AS kwh
        FROM telemetry t
        JOIN assets a ON a.did = t.did
        WHERE a.asset_type = 'meter'
          AND t.device_ts >= $1 AND t.device_ts < $2
        GROUP BY a.did
        """,
        start,
        end,
    )
    production = sum(float(r["kwh"]) for r in inverter_rows)
    consumption = [(r["did"], float(r["kwh"])) for r in meter_rows if float(r["kwh"]) > 0]
    return production, consumption


def allocate(production_kwh: float, consumers: list[tuple[str, float]]) -> tuple[list[tuple[str, float]], float]:
    """Pro-rata allocation. Returns (allocations, surplus)."""
    total_demand = sum(c[1] for c in consumers)
    if production_kwh <= 0 or total_demand <= 0:
        return [], max(production_kwh, 0.0)

    if production_kwh >= total_demand:
        allocations = [(did, kwh) for did, kwh in consumers]
        surplus = production_kwh - total_demand
    else:
        ratio = production_kwh / total_demand
        allocations = [(did, round(kwh * ratio, 4)) for did, kwh in consumers]
        surplus = 0.0
    return allocations, surplus


async def offer_surplus(http: httpx.AsyncClient, surplus_kwh: float) -> dict[str, Any] | None:
    if surplus_kwh <= 0 or not GSY_URL:
        return None
    try:
        resp = await http.post(
            f"{GSY_URL}/api/offers",
            json={"energy_kwh": surplus_kwh, "price_eur_kwh": INTERNAL_PRICE_EUR_KWH * 1.1},
            headers={"Authorization": f"Bearer {GSY_TOKEN}"} if GSY_TOKEN else {},
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("GSY-e offer failed: %s", exc)
        return None


async def run_once(pool: asyncpg.Pool, http: httpx.AsyncClient) -> dict[str, Any]:
    end = datetime.now(tz=timezone.utc).replace(second=0, microsecond=0)
    async with pool.acquire() as conn:
        production, consumers = await gather_window(conn, end)
        allocations, surplus = allocate(production, consumers)
        for did, kwh in allocations:
            await conn.execute(
                "INSERT INTO energy_shares (asset, kwh, price, share_time) VALUES ($1, $2, $3, $4)",
                did,
                kwh,
                INTERNAL_PRICE_EUR_KWH,
                end,
            )
    offer = await offer_surplus(http, surplus)
    log.info(
        "allocated production=%.3fkWh across %d consumers, surplus=%.3fkWh, offer=%s",
        production,
        len(allocations),
        surplus,
        bool(offer),
    )
    return {"production_kwh": production, "allocations": len(allocations), "surplus_kwh": surplus, "offer": offer}


async def main() -> None:
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
    async with httpx.AsyncClient() as http:
        try:
            while True:
                try:
                    await run_once(pool, http)
                except Exception as exc:  # noqa: BLE001
                    log.exception("allocation cycle failed: %s", exc)
                await asyncio.sleep(INTERVAL_MIN * 60)
        finally:
            await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
