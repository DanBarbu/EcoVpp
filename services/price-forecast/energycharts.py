"""Token-free EU day-ahead price connector (Energy-Charts / Fraunhofer ISE).

https://api.energy-charts.info — a public, no-auth REST API maintained by
Fraunhofer ISE that serves day-ahead spot prices for European bidding zones.
This is the default market source for the correlation/calibration so the whole
pipeline runs with NO ENTSO-E token, no registration, no secret.

Endpoint:
    GET https://api.energy-charts.info/price?bzn=<bzn>&start=YYYY-MM-DD&end=YYYY-MM-DD
Response:
    {"unix_seconds":[...], "price":[...], "unit":"EUR/MWh", ...}

Bidding-zone codes (`bzn`) differ from ENTSO-E EICs; see zones.Zone.ec.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx

Series = list[tuple[int, float]]

ENERGY_CHARTS_URL = os.getenv("ENERGY_CHARTS_URL", "https://api.energy-charts.info/price")


def parse(payload: dict) -> Series:
    secs = payload.get("unix_seconds") or []
    prices = payload.get("price") or []
    out: Series = [(int(t), float(p)) for t, p in zip(secs, prices) if p is not None]
    out.sort(key=lambda x: x[0])
    return out


def day_ahead(bzn: str, start: datetime, end: datetime, client: httpx.Client | None = None) -> Series:
    """Fetch day-ahead prices for bidding zone `bzn` over [start, end]."""
    if not bzn:
        raise ValueError("empty bidding-zone code (zone has no Energy-Charts mapping)")
    owned = client is None
    client = client or httpx.Client(timeout=20.0)
    try:
        params = {
            "bzn": bzn,
            "start": start.astimezone(timezone.utc).strftime("%Y-%m-%d"),
            "end": end.astimezone(timezone.utc).strftime("%Y-%m-%d"),
        }
        resp = client.get(ENERGY_CHARTS_URL, params=params)
        resp.raise_for_status()
        return parse(resp.json())
    finally:
        if owned:
            client.close()


def window(bzn: str, days: int, client: httpx.Client | None = None) -> Series:
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=days)
    return day_ahead(bzn, start, end, client=client)
