"""Correlation check + data-driven calibration against OPCOM (RO day-ahead).

Two adjustment paths, selected by the measured Pearson correlation between the
weather-driven model and the OPCOM actuals:

  r >= threshold (default 0.90)
      Keep the merit-order model. Optionally refit its level via OLS so the
      magnitude tracks OPCOM, but the shape is already good enough.

  r <  threshold
      The pure-weather model can't track OPCOM (gas coupling, hydro, nuclear,
      cross-border flows aren't in the weather signal). Switch to OPCOM-ANCHORED
      mode: the day-ahead hourly baseline IS OPCOM, and the weather/METOC
      nowcast only shapes it to 10-minute resolution. This makes the delivered
      forecast track OPCOM by construction while keeping sub-hourly value. We
      also OLS-refit the merit-order coefficients as the offline fallback used
      when OPCOM is unavailable (real-time beyond the day-ahead horizon).

No numpy dependency — Pearson r and OLS are implemented directly.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass

Series = list[tuple[int, float]]

CORRELATION_THRESHOLD = float(os.getenv("CORRELATION_THRESHOLD", "0.90"))
CALIBRATION_FILE = os.getenv("CALIBRATION_FILE", "calibration.json")


@dataclass
class Calibration:
    mode: str            # "merit_order" | "anchored"
    p_zero: float        # EUR/MWh at zero residual load (refit intercept)
    slope: float         # EUR/MWh per MW of residual load (refit slope)
    correlation: float   # Pearson r of model vs OPCOM over the backtest window
    n: int               # number of aligned hourly points used
    threshold: float
    fitted_at: float


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2 or len(ys) != n:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return 0.0
    return sxy / (sxx ** 0.5 * syy ** 0.5)


def ols(x: list[float], y: list[float]) -> tuple[float, float]:
    """Return (slope, intercept) for y ≈ slope*x + intercept."""
    n = len(x)
    if n < 2:
        return 0.0, (y[0] if y else 0.0)
    mx = sum(x) / n
    my = sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    sxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    slope = sxy / sxx if sxx else 0.0
    intercept = my - slope * mx
    return slope, intercept


def _hourly(series: Series) -> dict[int, float]:
    """Bucket a (possibly sub-hourly) series into hour-start → mean value."""
    buckets: dict[int, list[float]] = {}
    for ts, v in series:
        hour = ts - (ts % 3600)
        buckets.setdefault(hour, []).append(v)
    return {h: sum(vs) / len(vs) for h, vs in buckets.items()}


def align(a: Series, b: Series) -> tuple[list[float], list[float], list[int]]:
    """Align two series on common hour-start timestamps."""
    ha, hb = _hourly(a), _hourly(b)
    hours = sorted(set(ha) & set(hb))
    return [ha[h] for h in hours], [hb[h] for h in hours], hours


def evaluate(model_price: Series, opcom_price: Series,
             residual_load: Series | None = None,
             threshold: float = CORRELATION_THRESHOLD) -> Calibration:
    """Correlate model vs OPCOM and produce a calibration."""
    mp, op, _ = align(model_price, opcom_price)
    r = pearson(mp, op)

    # Refit merit-order coefficients from (residual_load_MW → opcom_price) when
    # residual load is available; otherwise from (model_price → opcom_price).
    if residual_load is not None:
        rl, op2, _ = align(residual_load, opcom_price)
        rl_mw = [v / 1000.0 for v in rl]
        slope, intercept = ols(rl_mw, op2)
    else:
        slope, intercept = ols(mp, op)

    mode = "merit_order" if r >= threshold else "anchored"
    return Calibration(
        mode=mode,
        p_zero=round(intercept, 3),
        slope=round(slope, 4),
        correlation=round(r, 4),
        n=len(mp),
        threshold=threshold,
        fitted_at=time.time(),
    )


def save(cal: Calibration, path: str = CALIBRATION_FILE) -> None:
    with open(path, "w") as fh:
        json.dump(asdict(cal), fh, indent=2)


def load(path: str = CALIBRATION_FILE) -> Calibration | None:
    try:
        with open(path) as fh:
            return Calibration(**json.load(fh))
    except (FileNotFoundError, TypeError, ValueError):
        return None
