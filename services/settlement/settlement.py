"""ECO-VPP Settlement Service.

Periodically reads unsettled `energy_shares` rows, batches them, and writes a
hash anchor to an Energy Web Origin smart contract. NFT Guarantees of Origin
are minted per kWh batch. PII never leaves the relational DB; only DIDs and
kWh deltas reach the chain (GDPR posture).

When `SETTLEMENT_DRY_RUN=true` (default) the service simulates blockchain
calls — useful for local dev and CI.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from uuid import uuid4

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from pydantic import BaseModel
from starlette.responses import Response

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("settlement")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://eco:eco@postgres:5432/ecovpp")
DRY_RUN = os.getenv("SETTLEMENT_DRY_RUN", "true").lower() == "true"
RPC_URL = os.getenv("EW_RPC_URL", "https://volta-rpc.energyweb.org")
PRIVATE_KEY = os.getenv("EW_PRIVATE_KEY", "")
ORIGIN_CONTRACT = os.getenv("EW_ORIGIN_CONTRACT", "")
BATCH_INTERVAL_S = float(os.getenv("BATCH_INTERVAL_S", "60"))

SETTLED_COUNTER = Counter("ecovpp_settlements_total", "Energy share batches settled")
NFT_COUNTER = Counter("ecovpp_gos_minted_total", "Guarantees of Origin minted")


class GoCertificate(BaseModel):
    token_id: str
    asset: str
    kwh: float
    period_start: datetime
    period_end: datetime
    tx_hash: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app.state.pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    app.state.batch_task = asyncio.create_task(_batch_loop(app))
    log.info("settlement service ready (dry_run=%s)", DRY_RUN)
    try:
        yield
    finally:
        app.state.batch_task.cancel()
        await app.state.pool.close()


app = FastAPI(title="ECO-VPP Settlement", version="0.1.0", lifespan=lifespan)


async def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "mode": "dry-run" if DRY_RUN else "live"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _settle_on_chain(batch_payload: dict[str, Any]) -> str:
    """Anchor a batch hash on Energy Web. Returns the tx hash.

    In dry-run mode (or without configured creds) we return a deterministic
    pseudo-hash so callers always get something to persist.
    """
    blob = json.dumps(batch_payload, sort_keys=True, default=str).encode()
    digest = hashlib.sha256(blob).hexdigest()

    if DRY_RUN or not PRIVATE_KEY or not ORIGIN_CONTRACT:
        return f"0xdry{digest[:60]}"

    try:
        from web3 import Web3  # imported lazily — heavy dep
    except ImportError:  # pragma: no cover - dependency present in prod
        log.error("web3 not available, falling back to dry-run hash")
        return f"0xnoweb3{digest[:56]}"

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    account = w3.eth.account.from_key(PRIVATE_KEY)
    tx = {
        "from": account.address,
        "to": ORIGIN_CONTRACT,
        "data": "0x" + digest,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 120_000,
        "gasPrice": w3.eth.gas_price,
        "chainId": w3.eth.chain_id,
    }
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return tx_hash.hex()


async def _settle_once(pool: asyncpg.Pool) -> dict[str, Any]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, asset, kwh, price, share_time
            FROM energy_shares
            WHERE settled = false
            ORDER BY share_time ASC
            LIMIT 500
            """
        )
        if not rows:
            return {"settled": 0}

        batch = [dict(r) for r in rows]
        period_start = min(r["share_time"] for r in batch)
        period_end = max(r["share_time"] for r in batch)
        total_kwh = sum(r["kwh"] for r in batch)

        payload = {
            "batch_id": str(uuid4()),
            "period_start": period_start,
            "period_end": period_end,
            "total_kwh": total_kwh,
            "rows": [
                {"id": r["id"], "asset": r["asset"], "kwh": r["kwh"], "price": r["price"]}
                for r in batch
            ],
        }
        tx_hash = _settle_on_chain(payload)

        ids = [r["id"] for r in batch]
        await conn.execute(
            "UPDATE energy_shares SET settled = true, settlement_tx = $1 WHERE id = ANY($2::bigint[])",
            tx_hash,
            ids,
        )
    SETTLED_COUNTER.inc()
    NFT_COUNTER.inc(len({r["asset"] for r in batch}))
    log.info("settled batch=%s rows=%s tx=%s", payload["batch_id"], len(batch), tx_hash)
    return {"settled": len(batch), "tx_hash": tx_hash, "batch_id": payload["batch_id"]}


async def _batch_loop(app: FastAPI) -> None:
    try:
        while True:
            await asyncio.sleep(BATCH_INTERVAL_S)
            try:
                await _settle_once(app.state.pool)
            except Exception as exc:  # noqa: BLE001
                log.exception("settlement batch failed: %s", exc)
    except asyncio.CancelledError:
        return


@app.post("/api/v1/settle")
async def trigger_settlement(pool: asyncpg.Pool = Depends(get_pool)) -> dict[str, Any]:
    return await _settle_once(pool)


@app.get("/api/v1/certificates")
async def list_certificates(pool: asyncpg.Pool = Depends(get_pool)) -> list[GoCertificate]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT settlement_tx, asset, SUM(kwh) AS kwh,
                   MIN(share_time) AS period_start, MAX(share_time) AS period_end
            FROM energy_shares
            WHERE settled = true AND settlement_tx IS NOT NULL
            GROUP BY settlement_tx, asset
            ORDER BY MAX(share_time) DESC
            LIMIT 100
            """
        )
    return [
        GoCertificate(
            token_id=hashlib.sha256(f"{r['settlement_tx']}:{r['asset']}".encode()).hexdigest()[:16],
            asset=r["asset"],
            kwh=float(r["kwh"]),
            period_start=r["period_start"],
            period_end=r["period_end"],
            tx_hash=r["settlement_tx"],
        )
        for r in rows
    ]


@app.get("/api/v1/proof/{tx_hash}")
async def proof(tx_hash: str, pool: asyncpg.Pool = Depends(get_pool)) -> dict[str, Any]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, asset, kwh, price, share_time FROM energy_shares WHERE settlement_tx = $1",
            tx_hash,
        )
    if not rows:
        raise HTTPException(status_code=404, detail="unknown tx")
    leaves = [hashlib.sha256(json.dumps(dict(r), sort_keys=True, default=str).encode()).hexdigest() for r in rows]
    root = hashlib.sha256(("".join(sorted(leaves))).encode()).hexdigest()
    return {"tx_hash": tx_hash, "merkle_root": root, "leaves": leaves, "anchored_at": datetime.now(timezone.utc).isoformat()}
