"""Weather-driven electricity price model.

A transparent residual-load merit-order model:

    residual_load = demand(temp, hour) - renewable_gen(gti, wind)
    price         = merit_order(residual_load)

It is deliberately simple and explainable — every coefficient is an env-var so
operators can calibrate to their bidding zone. The point is to turn the
high-resolution METOC/Open-Meteo weather nowcast into a 10-minute price curve
the flexibility-engine can act on; swap in a learned model later behind the
same `price_curve()` signature.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone

Series = list[tuple[int, float]]

# Installed capacities (community / zone scale), kW.
PV_CAPACITY_KW = float(os.getenv("PV_CAPACITY_KW", "5000"))
WIND_CAPACITY_KW = float(os.getenv("WIND_CAPACITY_KW", "2000"))
PV_SYS_EFFICIENCY = float(os.getenv("PV_SYS_EFFICIENCY", "0.85"))

# Demand profile, kW.
BASE_LOAD_KW = float(os.getenv("BASE_LOAD_KW", "3000"))
PEAK_LOAD_KW = float(os.getenv("PEAK_LOAD_KW", "9000"))
HEATING_KW_PER_DEGREE = float(os.getenv("HEATING_KW_PER_DEGREE", "180"))  # below 15°C
COOLING_KW_PER_DEGREE = float(os.getenv("COOLING_KW_PER_DEGREE", "140"))  # above 24°C

# Merit-order price mapping (EUR/MWh).
PRICE_FLOOR = float(os.getenv("PRICE_FLOOR_EUR_MWH", "0"))
PRICE_AT_ZERO_RESIDUAL = float(os.getenv("PRICE_AT_ZERO_EUR_MWH", "45"))
PRICE_CURVE_SLOPE = float(os.getenv("PRICE_SLOPE_EUR_PER_MW", "22"))  # per MW of residual load
PRICE_CAP = float(os.getenv("PRICE_CAP_EUR_MWH", "400"))

# Apply a persisted OPCOM calibration if present (written by validate.py).
# This recalibrates the merit-order curve to the RO market without code edits.
try:
    import calibration as _cal  # noqa: E402
    _c = _cal.load()
    if _c is not None:
        PRICE_AT_ZERO_RESIDUAL = _c.p_zero
        PRICE_CURVE_SLOPE = _c.slope
except Exception:  # noqa: BLE001 - calibration is optional
    _c = None


@dataclass
class PricePoint:
    ts: int
    price_eur_mwh: float
    residual_load_kw: float
    renewable_kw: float
    demand_kw: float


def _wind_power_kw(wind_ms: float) -> float:
    """Simplified turbine curve: cut-in 3 m/s, rated 12 m/s, cut-out 25 m/s."""
    if wind_ms < 3 or wind_ms >= 25:
        return 0.0
    if wind_ms >= 12:
        return WIND_CAPACITY_KW
    # cubic ramp between cut-in and rated
    frac = ((wind_ms - 3) / (12 - 3)) ** 3
    return WIND_CAPACITY_KW * frac


def _pv_power_kw(gti_w_m2: float) -> float:
    return PV_CAPACITY_KW * (gti_w_m2 / 1000.0) * PV_SYS_EFFICIENCY


def _demand_kw(temp_c: float, ts: int) -> float:
    hour = datetime.fromtimestamp(ts, tz=timezone.utc).hour + \
        datetime.fromtimestamp(ts, tz=timezone.utc).minute / 60.0
    # Two-peak daily shape (morning + evening).
    shape = 0.5 * (math.sin((hour - 8) / 24 * 2 * math.pi) + math.sin((hour - 19) / 12 * 2 * math.pi))
    shape = max(0.0, min(1.0, 0.5 + 0.5 * shape))
    load = BASE_LOAD_KW + (PEAK_LOAD_KW - BASE_LOAD_KW) * shape
    if temp_c < 15:
        load += (15 - temp_c) * HEATING_KW_PER_DEGREE
    elif temp_c > 24:
        load += (temp_c - 24) * COOLING_KW_PER_DEGREE
    return load


def _merit_order_price(residual_load_kw: float) -> float:
    residual_mw = residual_load_kw / 1000.0
    price = PRICE_AT_ZERO_RESIDUAL + PRICE_CURVE_SLOPE * residual_mw
    return max(PRICE_FLOOR, min(PRICE_CAP, price))


def _align(*series: Series) -> list[int]:
    """Common timestamps across series (intersection, ascending)."""
    if not series or any(not s for s in series):
        return []
    sets = [set(t for t, _ in s) for s in series]
    common = set.intersection(*sets)
    return sorted(common)


def price_curve(gti: Series, wind: Series, temperature: Series) -> list[PricePoint]:
    gmap = dict(gti)
    wmap = dict(wind)
    tmap = dict(temperature)
    out: list[PricePoint] = []
    for ts in _align(gti, wind, temperature):
        renewable = _pv_power_kw(gmap[ts]) + _wind_power_kw(wmap[ts])
        demand = _demand_kw(tmap[ts], ts)
        residual = demand - renewable
        out.append(PricePoint(
            ts=ts,
            price_eur_mwh=round(_merit_order_price(residual), 2),
            residual_load_kw=round(residual, 1),
            renewable_kw=round(renewable, 1),
            demand_kw=round(demand, 1),
        ))
    return out


def _hour_start(ts: int) -> int:
    return ts - (ts % 3600)


def price_curve_anchored(opcom_hourly: Series, gti: Series, wind: Series,
                         temperature: Series) -> list[PricePoint]:
    """OPCOM-anchored 10-minute curve.

    The hourly day-ahead baseline is OPCOM; the weather model only shapes the
    intra-hour deviation. For each 10-min step we take the OPCOM price for that
    hour and nudge it by the within-hour residual-load deviation from the hour's
    mean, scaled by the (calibrated) merit-order slope. This tracks OPCOM at
    hourly resolution by construction while preserving sub-hourly weather value.
    """
    op = dict(opcom_hourly)
    gmap, wmap, tmap = dict(gti), dict(wind), dict(temperature)
    steps = _align(gti, wind, temperature)

    # Hour-mean residual load for the deviation term.
    by_hour: dict[int, list[float]] = {}
    residual_at: dict[int, float] = {}
    for ts in steps:
        residual = _demand_kw(tmap[ts], ts) - (_pv_power_kw(gmap[ts]) + _wind_power_kw(wmap[ts]))
        residual_at[ts] = residual
        by_hour.setdefault(_hour_start(ts), []).append(residual)
    hour_mean = {h: sum(v) / len(v) for h, v in by_hour.items()}

    out: list[PricePoint] = []
    for ts in steps:
        h = _hour_start(ts)
        base = op.get(h)
        if base is None:  # no OPCOM coverage for this hour → fall back to merit order
            base = _merit_order_price(residual_at[ts])
        dev_mw = (residual_at[ts] - hour_mean.get(h, residual_at[ts])) / 1000.0
        price = max(PRICE_FLOOR, min(PRICE_CAP, base + PRICE_CURVE_SLOPE * dev_mw))
        renewable = _pv_power_kw(gmap[ts]) + _wind_power_kw(wmap[ts])
        out.append(PricePoint(
            ts=ts,
            price_eur_mwh=round(price, 2),
            residual_load_kw=round(residual_at[ts], 1),
            renewable_kw=round(renewable, 1),
            demand_kw=round(_demand_kw(tmap[ts], ts), 1),
        ))
    return out
