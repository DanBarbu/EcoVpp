"""ECO-VPP Price Forecast service.

Combines the Open-Meteo + METOC nowcast weather pipeline with a residual-load
merit-order model to publish a 10-minute-resolution electricity price curve.

Endpoints
  GET /healthz
  GET /metrics
  GET /api/v1/price/forecast        full curve (10-min steps)
  GET /api/v1/price/current         the price point nearest to now
  GET /api/v1/price/next?minutes=10 price expected `minutes` ahead
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from starlette.responses import Response

import model
import weather

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("price-forecast")

HORIZON_HOURS = int(os.getenv("PRICE_HORIZON_HOURS", "6"))
CACHE_TTL_S = int(os.getenv("PRICE_CACHE_TTL_S", "300"))

CUR_PRICE = Gauge("ecovpp_price_forecast_current_eur_mwh", "Current modelled price")
HORIZON_G = Gauge("ecovpp_price_forecast_horizon_hours", "Forecast horizon (hours)")
RES_G = Gauge("ecovpp_price_forecast_resolution_min", "Forecast resolution (minutes)")

app = FastAPI(title="ECO-VPP Price Forecast", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_cache: dict[str, object] = {"ts": 0.0, "points": [], "provider": "", "resolution_min": 0}


def _refresh(force: bool = False) -> None:
    now = time.time()
    if not force and (now - float(_cache["ts"])) < CACHE_TTL_S and _cache["points"]:
        return
    with httpx.Client(timeout=12.0) as c:
        wx = weather.fetch(horizon_hours=HORIZON_HOURS, client=c)
    points = model.price_curve(wx.gti, wx.wind, wx.temperature)
    _cache.update({
        "ts": now,
        "points": points,
        "provider": wx.provider,
        "resolution_min": wx.resolution_min,
    })
    if points:
        nearest = _nearest(points)
        CUR_PRICE.set(nearest.price_eur_mwh)
        HORIZON_G.set(wx.horizon_hours())
        RES_G.set(wx.resolution_min)
    log.info("refreshed: %d points, provider=%s, res=%dmin", len(points), wx.provider, wx.resolution_min)


def _nearest(points: list[model.PricePoint], at: float | None = None) -> model.PricePoint:
    at = at if at is not None else time.time()
    return min(points, key=lambda p: abs(p.ts - at))


def _serialize(p: model.PricePoint) -> dict:
    return {
        "timestamp": datetime.fromtimestamp(p.ts, tz=timezone.utc).isoformat(),
        "price_eur_mwh": p.price_eur_mwh,
        "price_eur_kwh": round(p.price_eur_mwh / 1000.0, 5),
        "residual_load_kw": p.residual_load_kw,
        "renewable_kw": p.renewable_kw,
        "demand_kw": p.demand_kw,
    }


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "provider": _cache.get("provider") or "uninitialised"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/v1/price/forecast")
def forecast() -> dict:
    _refresh()
    pts = _cache["points"]  # type: ignore[assignment]
    return {
        "provider": _cache["provider"],
        "resolution_min": _cache["resolution_min"],
        "count": len(pts),
        "points": [_serialize(p) for p in pts],
    }


@app.get("/api/v1/price/current")
def current() -> dict:
    _refresh()
    pts = _cache["points"]  # type: ignore[assignment]
    if not pts:
        return {"error": "no forecast available"}
    return _serialize(_nearest(pts))


@app.get("/api/v1/price/next")
def nxt(minutes: int = Query(10, ge=0, le=360)) -> dict:
    _refresh()
    pts = _cache["points"]  # type: ignore[assignment]
    if not pts:
        return {"error": "no forecast available"}
    return _serialize(_nearest(pts, at=time.time() + minutes * 60))
