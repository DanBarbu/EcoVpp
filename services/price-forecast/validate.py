"""Correlate the price model against OPCOM (RO day-ahead) and calibrate.

Run where there is network egress and an ENTSO-E token:

    export ENTSOE_TOKEN=...            # free, from transparency.entsoe.eu
    python validate.py --days 14

or with a manually exported OPCOM CSV (timestamp,price_eur_mwh):

    OPCOM_CSV=opcom_pzu.csv python validate.py --days 14

Behaviour
  * Fetches OPCOM day-ahead prices and the matching Open-Meteo weather for the
    backtest window, builds the model price series, and reports Pearson r.
  * If r >= threshold (default 0.90): writes a merit-order calibration (level
    refit) and reports PASS.
  * If r < threshold: writes an OPCOM-ANCHORED calibration (and refit merit-order
    coefficients as the offline fallback) and reports that anchoring is enabled.

The price-forecast service and model.py pick up calibration.json automatically.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

import httpx

import calibration
import model
import opcom
import weather


def _weather_window(hours: int, client: httpx.Client) -> weather.WeatherForecast:
    # weather.fetch pulls a forward window; for backtesting against OPCOM you
    # would point SITE_LAT/LON at the RO zone centroid. Open-Meteo also serves
    # past days via its archive API; see README for the archive variant.
    return weather.fetch(horizon_hours=hours, client=client)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="backtest window length")
    ap.add_argument("--threshold", type=float, default=calibration.CORRELATION_THRESHOLD)
    ap.add_argument("--dry-run", action="store_true", help="report only, don't write calibration.json")
    args = ap.parse_args()

    with httpx.Client(timeout=30.0) as client:
        # 1. OPCOM actuals
        opcom_series: opcom.Series = []
        try:
            for d in range(args.days):
                day = datetime.now(tz=timezone.utc) - timedelta(days=d + 1)
                opcom_series += opcom.day_ahead(day, client=client)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR fetching OPCOM/ENTSO-E data: {exc}", file=sys.stderr)
            print("Provide ENTSOE_TOKEN or OPCOM_CSV. See module docstring.", file=sys.stderr)
            return 2
        if not opcom_series:
            print("No OPCOM prices returned for the window.", file=sys.stderr)
            return 2

        # 2. Weather + model series over the same span
        wx = _weather_window(hours=args.days * 24, client=client)
        model_points = model.price_curve(wx.gti, wx.wind, wx.temperature)

    model_price = [(p.ts, p.price_eur_mwh) for p in model_points]
    residual = [(p.ts, p.residual_load_kw) for p in model_points]

    cal = calibration.evaluate(model_price, opcom_series, residual_load=residual, threshold=args.threshold)

    print(f"OPCOM points: {len(opcom_series)} | aligned hours: {cal.n}")
    print(f"Pearson correlation (model vs OPCOM): {cal.correlation:.3f}")
    print(f"Threshold: {cal.threshold:.2f}")
    if cal.correlation >= cal.threshold:
        print(f"PASS — correlation ≥ {cal.threshold:.0%}. Merit-order model retained "
              f"(level refit: p_zero={cal.p_zero}, slope={cal.slope}).")
    else:
        print(f"BELOW THRESHOLD — switching to OPCOM-ANCHORED mode. The day-ahead "
              f"baseline will track OPCOM; weather/METOC shapes the 10-min curve. "
              f"Offline merit-order fallback refit: p_zero={cal.p_zero}, slope={cal.slope}.")

    if args.dry_run:
        print("(dry-run: calibration.json not written)")
    else:
        calibration.save(cal)
        print(f"Wrote {calibration.CALIBRATION_FILE} (mode={cal.mode}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
