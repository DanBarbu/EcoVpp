"""Correlate the price model against real EU day-ahead markets and calibrate.

Token-free default (Energy-Charts / Fraunhofer ISE); optional ENTSO-E source
when ENTSOE_TOKEN is set:

    python validate.py --zone RO --days 14          # Romania
    python validate.py --all --days 14              # every EU bidding zone

For each zone it fetches the day-ahead price for the past `--days` window and
the matching HISTORICAL weather from the Open-Meteo archive (so the model
series and the market series cover the same hours — vs. the forecast endpoint,
which only serves forward in time and produced misleading n≈22 correlations).

  r >= threshold (default 0.90) -> calibration.<zone>.json mode=merit_order
  r <  threshold                -> calibration.<zone>.json mode=anchored

Failures are no longer silent: every zone that doesn't produce a calibration
gets a reason recorded in the printed report (and in REPORT.txt when run via
the GitHub workflow), so missing zones are diagnosable without log digging.
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
                    client: httpx.Client, write: bool
                    ) -> tuple[calibration.Calibration | None, str]:
    """Return (calibration_or_None, reason). reason is "" on success."""
    z = zones.get(zone_code)
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=days)

    try:
        market = _market_for_zone(zone_code, days, source, client)
    except Exception as exc:  # noqa: BLE001
        return None, f"market fetch failed: {exc}"
    if not market:
        return None, "market returned empty series (zone may not be covered by this source)"

    try:
        wx = weather.archive(start=start, end=end, lat=z.lat, lon=z.lon, client=client)
    except Exception as exc:  # noqa: BLE001
        return None, f"weather archive failed: {exc}"
    if not wx.gti:
        return None, "weather archive returned no data"

    pts = model.price_curve(wx.gti, wx.wind, wx.temperature)
    if not pts:
        return None, "model produced empty curve (no aligned weather samples)"

    model_price = [(p.ts, p.price_eur_mwh) for p in pts]
    residual = [(p.ts, p.residual_load_kw) for p in pts]
    cal = calibration.evaluate(model_price, market, residual_load=residual, threshold=threshold)
    if cal.n == 0:
        return None, "no overlapping hours between model and market"
    if write:
        calibration.save(cal, calibration.path_for(zone_code))
    return cal, ""


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
    print(f"Source: {args.source} | window: {args.days}d | threshold: {args.threshold:.0%}")
    print(f"Weather: open-meteo-archive (historical, matches market window)\n")

    results: dict[str, float] = {}
    failures: list[tuple[str, str]] = []
    with httpx.Client(timeout=30.0) as client:
        for code in codes:
            cal, reason = _calibrate_zone(code, args.days, args.threshold, args.source,
                                          client, write=not args.dry_run)
            if cal is None:
                z = zones.get(code)
                failures.append((code, reason))
                print(f"[{code}] {z.name:22s} SKIPPED — {reason}")
                continue
            results[code] = cal.correlation
            status = "PASS" if cal.correlation >= args.threshold else "ANCHOR"
            z = zones.get(code)
            print(f"[{code}] {z.name:22s} r={cal.correlation:+.3f} n={cal.n:4d} "
                  f"-> {cal.mode:11s} [{status}]")

    print()
    if results:
        anchored = sum(1 for c in results.values() if c < args.threshold)
        print(f"Summary: {len(results)} zones calibrated, mean r="
              f"{sum(results.values())/len(results):+.3f}, "
              f"{anchored} below {args.threshold:.0%} -> anchored to market price.")
    else:
        print("No zones calibrated.")
    if failures:
        print(f"Skipped: {len(failures)} zone(s) — {', '.join(c for c, _ in failures)}")
    return 0 if results else 2


if __name__ == "__main__":
    raise SystemExit(main())
