"""Correlate the price model against real EU day-ahead markets and calibrate.

Run where there is network egress and an ENTSO-E token (free, from
https://transparency.entsoe.eu):

    export ENTSOE_TOKEN=...
    python validate.py --zone RO --days 14          # Romania (OPCOM)
    python validate.py --all --days 14              # every EU bidding zone

For each zone it fetches the day-ahead price (ENTSO-E A44) and the matching
Open-Meteo weather at the zone centroid, builds the model price series, and
measures Pearson correlation. Per-zone result:

  r >= threshold (default 0.90) -> calibration.<zone>.json mode=merit_order
  r <  threshold                -> calibration.<zone>.json mode=anchored

The RO CSV fallback (OPCOM_CSV) still works for --zone RO with no token.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

import httpx

import calibration
import energycharts
import markets
import model
import weather
import zones


def _market_for_zone(zone_code: str, days: int, source: str,
                     client: httpx.Client) -> list[tuple[int, float]]:
    """Fetch the day-ahead price series for a zone from the chosen source.

    `energycharts` (default) needs no token. `entsoe` needs ENTSOE_TOKEN but
    offers the official source. Energy-Charts serves a whole window in one call.
    """
    z = zones.get(zone_code)
    if source == "entsoe":
        series: list[tuple[int, float]] = []
        for d in range(days):
            day = datetime.now(tz=timezone.utc) - timedelta(days=d + 1)
            series += markets.day_ahead(z.eic, day=day, client=client)
        return series
    if not z.ec:
        raise ValueError(f"zone {zone_code} has no Energy-Charts mapping; use --source entsoe")
    return energycharts.window(z.ec, days, client=client)


def _calibrate_zone(zone_code: str, days: int, threshold: float, source: str,
                    client: httpx.Client, write: bool) -> calibration.Calibration | None:
    z = zones.get(zone_code)
    try:
        market = _market_for_zone(zone_code, days, source, client)
    except Exception as exc:  # noqa: BLE001
        print(f"[{zone_code}] ERROR fetching day-ahead: {exc}", file=sys.stderr)
        return None
    if not market:
        print(f"[{zone_code}] no prices returned", file=sys.stderr)
        return None

    wx = weather.fetch(horizon_hours=days * 24, client=client, lat=z.lat, lon=z.lon)
    pts = model.price_curve(wx.gti, wx.wind, wx.temperature)
    model_price = [(p.ts, p.price_eur_mwh) for p in pts]
    residual = [(p.ts, p.residual_load_kw) for p in pts]

    cal = calibration.evaluate(model_price, market, residual_load=residual, threshold=threshold)
    status = "PASS" if cal.correlation >= threshold else "ANCHOR"
    print(f"[{zone_code}] {z.name:22s} r={cal.correlation:+.3f} n={cal.n:4d} "
          f"-> {cal.mode:11s} [{status}]")
    if write:
        calibration.save(cal, calibration.path_for(zone_code))
    return cal


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zone", default="RO", help="zone code (see zones.py)")
    ap.add_argument("--all", action="store_true", help="calibrate every EU zone")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--threshold", type=float, default=calibration.CORRELATION_THRESHOLD)
    ap.add_argument("--source", choices=["energycharts", "entsoe"], default="energycharts",
                    help="market data source (energycharts is token-free; entsoe needs ENTSOE_TOKEN)")
    ap.add_argument("--dry-run", action="store_true", help="report only; don't write files")
    args = ap.parse_args()

    codes = zones.all_codes() if args.all else [args.zone]
    print(f"Source: {args.source} | window: {args.days}d | threshold: {args.threshold:.0%}\n")
    results: dict[str, float] = {}
    with httpx.Client(timeout=30.0) as client:
        for code in codes:
            cal = _calibrate_zone(code, args.days, args.threshold, args.source, client,
                                  write=not args.dry_run)
            if cal:
                results[code] = cal.correlation

    if not results:
        print("No zones calibrated (check network / source availability).", file=sys.stderr)
        return 2

    anchored = sum(1 for c in results.values() if c < args.threshold)
    print(f"\nSummary: {len(results)} zones, mean r="
          f"{sum(results.values())/len(results):+.3f}, "
          f"{anchored} below {args.threshold:.0%} -> anchored to market price.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
