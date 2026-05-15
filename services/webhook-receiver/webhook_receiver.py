import asyncio
import math
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

INGEST_TOKEN = os.environ.get("INGEST_TOKEN", "dev-token")
LOW_CONFIDENCE_THRESHOLD = 0.80

app = FastAPI(title="ECO-VPP webhook-receiver")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Asset(BaseModel):
    id: str
    did: str
    asset_type: str
    location: Optional[str] = None


class AssetCreate(BaseModel):
    did: str
    asset_type: str
    location: Optional[str] = None


class TelemetrySample(BaseModel):
    asset: str
    kwh: float
    price: float = 0.0
    time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = 1.0


_assets: dict[str, Asset] = {}
_shares: list[dict] = []
_verification_queue: list[dict] = []
_ws_clients: set[WebSocket] = set()


def require_ingest_token(x_ingest_token: str = Header(default="")) -> None:
    if x_ingest_token != INGEST_TOKEN:
        raise HTTPException(status_code=401, detail="invalid ingest token")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/assets")
def list_assets() -> dict:
    return {"assets": list(_assets.values())}


@app.post("/api/v1/assets", status_code=201)
def create_asset(body: AssetCreate) -> Asset:
    asset = Asset(id=str(uuid.uuid4()), **body.model_dump())
    _assets[asset.id] = asset
    return asset


@app.post("/api/v1/telemetry/ingest", dependencies=[Depends(require_ingest_token)])
def ingest(sample: TelemetrySample) -> dict:
    record = sample.model_dump(mode="json")
    if sample.confidence < LOW_CONFIDENCE_THRESHOLD:
        _verification_queue.append(record)
        return {"status": "queued_for_verification"}
    _shares.append(record)
    return {"status": "accepted"}


@app.get("/api/shares/latest")
def latest_shares(limit: int = 50) -> list[dict]:
    return list(reversed(_shares[-limit:]))


@app.get("/api/v1/verification/queue")
def verification_queue() -> list[dict]:
    return list(_verification_queue)


async def _broadcast(payload: dict) -> None:
    dead: list[WebSocket] = []
    for ws in _ws_clients:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)


@app.on_event("startup")
async def _start_incentive_loop() -> None:
    async def loop() -> None:
        while True:
            t = time.time()
            # Synthetic price wave when no external signal is wired in.
            signal = (math.sin(t / 60.0) + 1) / 2  # 0..1 curtailment
            price = round(0.05 + 0.25 * signal, 4)
            await _broadcast({"price": price, "signal": signal, "ts": t})
            await asyncio.sleep(5)

    asyncio.create_task(loop())


@app.websocket("/ws")
async def ws_incentive(ws: WebSocket) -> None:
    await ws.accept()
    _ws_clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)
