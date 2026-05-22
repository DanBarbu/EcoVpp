"""Romania day-ahead price connector (OPCOM PZU via ENTSO-E).

OPCOM runs the Romanian day-ahead market (PZU). Its results for the RO bidding
zone are published machine-readably on the ENTSO-E Transparency Platform, which
is the canonical programmatic source (OPCOM's own site has no clean public API).

Primary source : ENTSO-E Transparency Platform REST API, documentType A44
                 (day-ahead prices), bidding zone RO = 10YRO-TEL------P.
                 Needs a free security token (env ENTSOE_TOKEN). Register at
                 https://transparency.entsoe.eu → My Account → request API access.

Fallback       : a local CSV (env OPCOM_CSV) with columns `timestamp,price_eur_mwh`
                 — e.g. an OPCOM PZU report you exported manually.

Returns hourly (timestamp_epoch, price_eur_mwh) tuples, ascending.
"""
from __future__ import annotations

import csv
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import httpx

Series = list[tuple[int, float]]

ENTSOE_URL = os.getenv("ENTSOE_URL", "https://web-api.tp.entsoe.eu/api")
ENTSOE_TOKEN = os.getenv("ENTSOE_TOKEN", "")
RO_ZONE_EIC = os.getenv("RO_ZONE_EIC", "10YRO-TEL------P")
OPCOM_CSV = os.getenv("OPCOM_CSV", "")


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M")


def from_entsoe(day_start: datetime, day_end: datetime, client: httpx.Client | None = None) -> Series:
    """Fetch RO day-ahead prices from ENTSO-E for [day_start, day_end)."""
    if not ENTSOE_TOKEN:
        raise RuntimeError("ENTSOE_TOKEN not set — cannot query ENTSO-E. "
                           "Set it, or provide OPCOM_CSV for the fallback path.")
    owned = client is None
    client = client or httpx.Client(timeout=20.0)
    try:
        params = {
            "securityToken": ENTSOE_TOKEN,
            "documentType": "A44",
            "in_Domain": RO_ZONE_EIC,
            "out_Domain": RO_ZONE_EIC,
            "periodStart": _fmt(day_start),
            "periodEnd": _fmt(day_end),
        }
        resp = client.get(ENTSOE_URL, params=params)
        resp.raise_for_status()
        return _parse_a44(resp.text)
    finally:
        if owned:
            client.close()


def _parse_a44(xml_text: str) -> Series:
    """Parse an ENTSO-E A44 Publication_MarketDocument into an hourly series."""
    # Strip namespaces for simpler traversal.
    root = ET.fromstring(xml_text)
    ns = {"": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}

    def find_all(el, tag):
        return el.iter("{%s}%s" % (ns[""], tag)) if ns else el.iter(tag)

    out: Series = []
    for ts in find_all(root, "TimeSeries"):
        for period in (ts.iter("{%s}Period" % ns[""]) if ns else ts.iter("Period")):
            start_el = period.find("{%s}timeInterval/{%s}start" % (ns[""], ns[""])) if ns \
                else period.find("timeInterval/start")
            res_el = period.find("{%s}resolution" % ns[""]) if ns else period.find("resolution")
            if start_el is None or res_el is None:
                continue
            start = datetime.fromisoformat(start_el.text.replace("Z", "+00:00"))
            step_min = 60 if "60M" in (res_el.text or "") else 15 if "15M" in (res_el.text or "") else 60
            points = period.iter("{%s}Point" % ns[""]) if ns else period.iter("Point")
            for pt in points:
                pos_el = pt.find("{%s}position" % ns[""]) if ns else pt.find("position")
                amt_el = pt.find("{%s}price.amount" % ns[""]) if ns else pt.find("price.amount")
                if pos_el is None or amt_el is None:
                    continue
                pos = int(pos_el.text)
                t = start + timedelta(minutes=step_min * (pos - 1))
                out.append((int(t.timestamp()), float(amt_el.text)))
    out.sort(key=lambda x: x[0])
    return out


def from_csv(path: str | None = None) -> Series:
    """Read RO day-ahead prices from a local CSV (timestamp,price_eur_mwh).

    `timestamp` may be ISO-8601 or epoch seconds.
    """
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
            ts = int(raw) if raw.isdigit() else int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
            out.append((ts, float(price)))
    out.sort(key=lambda x: x[0])
    return out


def day_ahead(day: datetime | None = None, client: httpx.Client | None = None) -> Series:
    """Best-effort RO day-ahead price series for the given UTC day.

    Prefers ENTSO-E; falls back to a local CSV if no token is configured.
    """
    if OPCOM_CSV and not ENTSOE_TOKEN:
        return from_csv()
    day = (day or datetime.now(tz=timezone.utc)).replace(hour=0, minute=0, second=0, microsecond=0)
    return from_entsoe(day, day + timedelta(days=1), client=client)
