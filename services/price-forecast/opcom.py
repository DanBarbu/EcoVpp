"""Romania day-ahead price connector (OPCOM PZU).

Thin wrapper over the generic ENTSO-E connector (`markets.py`) for the RO
bidding zone, kept for backward compatibility and as the documented entry point
for the Romania case. New code should prefer `markets.day_ahead(eic)` with a
zone EIC from `zones.py`.

Source: ENTSO-E Transparency Platform, documentType A44, RO = 10YRO-TEL------P
(the canonical machine-readable carrier of the OPCOM PZU price). CSV fallback
via env OPCOM_CSV for manually exported OPCOM reports.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime, timezone

import httpx

import markets

Series = list[tuple[int, float]]

RO_ZONE_EIC = os.getenv("RO_ZONE_EIC", "10YRO-TEL------P")
OPCOM_CSV = os.getenv("OPCOM_CSV", "")


def from_csv(path: str | None = None) -> Series:
    """Read RO day-ahead prices from a local CSV (timestamp,price_eur_mwh)."""
    path = path or OPCOM_CSV
    if not path:
        raise RuntimeError("OPCOM_CSV not set")
    out: Series = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            raw = (row.get("timestamp") or row.get("time") or "").strip()
            price = row.get("price_eur_mwh") or row.get("price") or row.get("eur_mwh")
            if not raw or price in (None, ""):
                continue
            ts = int(raw) if raw.isdigit() else int(
                datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
            out.append((ts, float(price)))
    out.sort(key=lambda x: x[0])
    return out


def day_ahead(day: datetime | None = None, client: httpx.Client | None = None) -> Series:
    """RO day-ahead price series. Prefers ENTSO-E; CSV fallback if no token."""
    if OPCOM_CSV and not markets.ENTSOE_TOKEN:
        return from_csv()
    return markets.day_ahead(RO_ZONE_EIC, day=day, client=client)
