"""Generic ENTSO-E day-ahead price connector (any EU bidding zone).

documentType A44 (day-ahead prices) for an arbitrary bidding-zone EIC. This is
the canonical machine-readable source for every EU day-ahead market (OPCOM/RO,
EPEX/DE-FR-NL/BE/AT, OMIE/ES-PT, GME/IT, Nord Pool/Nordics-Baltics, etc.).

Needs a free token (env ENTSOE_TOKEN) from https://transparency.entsoe.eu.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import httpx

Series = list[tuple[int, float]]

ENTSOE_URL = os.getenv("ENTSOE_URL", "https://web-api.tp.entsoe.eu/api")
ENTSOE_TOKEN = os.getenv("ENTSOE_TOKEN", "")


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M")


def parse_a44(xml_text: str) -> Series:
    """Parse an ENTSO-E A44 Publication_MarketDocument into a price series."""
    root = ET.fromstring(xml_text)
    nsuri = root.tag.split("}")[0].strip("{") if "}" in root.tag else ""

    def q(tag: str) -> str:
        return f"{{{nsuri}}}{tag}" if nsuri else tag

    out: Series = []
    for ts in root.iter(q("TimeSeries")):
        for period in ts.iter(q("Period")):
            start_el = period.find(f"{q('timeInterval')}/{q('start')}")
            res_el = period.find(q("resolution"))
            if start_el is None or res_el is None:
                continue
            start = datetime.fromisoformat(start_el.text.replace("Z", "+00:00"))
            res = res_el.text or ""
            step = 60 if "60M" in res else 15 if "15M" in res else 30 if "30M" in res else 60
            for pt in period.iter(q("Point")):
                pos_el = pt.find(q("position"))
                amt_el = pt.find(q("price.amount"))
                if pos_el is None or amt_el is None:
                    continue
                t = start + timedelta(minutes=step * (int(pos_el.text) - 1))
                out.append((int(t.timestamp()), float(amt_el.text)))
    out.sort(key=lambda x: x[0])
    return out


def day_ahead(eic: str, day: datetime | None = None, client: httpx.Client | None = None) -> Series:
    """Fetch one UTC day of day-ahead prices for the given bidding-zone EIC."""
    if not ENTSOE_TOKEN:
        raise RuntimeError("ENTSOE_TOKEN not set — cannot query ENTSO-E.")
    day = (day or datetime.now(tz=timezone.utc)).replace(hour=0, minute=0, second=0, microsecond=0)
    owned = client is None
    client = client or httpx.Client(timeout=20.0)
    try:
        params = {
            "securityToken": ENTSOE_TOKEN,
            "documentType": "A44",
            "in_Domain": eic,
            "out_Domain": eic,
            "periodStart": _fmt(day),
            "periodEnd": _fmt(day + timedelta(days=1)),
        }
        resp = client.get(ENTSOE_URL, params=params)
        resp.raise_for_status()
        return parse_a44(resp.text)
    finally:
        if owned:
            client.close()
