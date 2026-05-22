"""Adapter for the METOC Lagrangian nowcasting platform.

The METOC platform (branch `claude/metoc-lagrangian-platform-XYLxL`, a separate
repo) produces high-resolution short-range weather nowcasts by Lagrangian
advection of the current irradiance / cloud / wind fields. It refines a coarse
NWP forecast (here: Open-Meteo) down to ~10-minute resolution for the next
hour, which materially improves intraday energy-price forecasting.

This module is the integration seam. Two ways to use it:

  1. **Drop-in the real code.** Implement `lagrangian_nowcast()` below using the
     METOC platform's advection routines (paste them in, or `pip install` the
     METOC package and import it). Keep the signature stable.

  2. **Run the fallback.** Until the METOC code is wired in, `refine()` uses a
     shape-preserving monotone interpolation (PCHIP-style, dependency-free) to
     upsample the coarse series to 10-minute steps. It is *not* a true nowcast
     — it won't beat persistence on cloud edges — but it keeps the whole
     pricing pipeline runnable and exercises the same data contract.

Data contract
-------------
A "series" is a list of (epoch_seconds:int, value:float) points, ascending in
time, in native units (e.g. W/m² for GTI, m/s for wind).
"""
from __future__ import annotations

import os
from typing import Callable

Series = list[tuple[int, float]]

# Set METOC_NOWCAST=1 (and provide an implementation) to use the real platform.
USE_METOC = os.getenv("METOC_NOWCAST", "0") == "1"
NOWCAST_HORIZON_MIN = int(os.getenv("NOWCAST_HORIZON_MIN", "60"))
NOWCAST_STEP_MIN = int(os.getenv("NOWCAST_STEP_MIN", "10"))


def lagrangian_nowcast(coarse: Series, wind: Series | None, horizon_min: int, step_min: int) -> Series:
    """Hook for the METOC Lagrangian advection nowcast.

    Replace the body with a call into the METOC platform. Expected behaviour:
    given the most recent coarse field samples (and optionally a wind series to
    advect along), return a high-resolution series covering `now .. now +
    horizon_min` at `step_min` resolution.

    >>> # from metoc.lagrangian import advect_field
    >>> # return advect_field(coarse, wind, horizon_min, step_min)
    """
    raise NotImplementedError(
        "METOC Lagrangian nowcast not wired in. Set METOC_NOWCAST=0 to use the "
        "interpolation fallback, or implement lagrangian_nowcast() with the "
        "platform's advection routines."
    )


# ----------------------------------------------------------------- fallback
def _pchip_like(t0: float, t1: float, v0: float, v1: float, m0: float, m1: float, t: float) -> float:
    """Cubic Hermite interpolation between two points with given slopes."""
    h = t1 - t0
    if h <= 0:
        return v0
    s = (t - t0) / h
    s2 = s * s
    s3 = s2 * s
    h00 = 2 * s3 - 3 * s2 + 1
    h10 = s3 - 2 * s2 + s
    h01 = -2 * s3 + 3 * s2
    h11 = s3 - s2
    return h00 * v0 + h10 * h * m0 + h01 * v1 + h11 * h * m1


def _monotone_slopes(pts: Series) -> list[float]:
    n = len(pts)
    if n < 2:
        return [0.0] * n
    secant = []
    for i in range(n - 1):
        dt = pts[i + 1][0] - pts[i][0]
        secant.append((pts[i + 1][1] - pts[i][1]) / dt if dt else 0.0)
    slopes = [secant[0]]
    for i in range(1, n - 1):
        if secant[i - 1] * secant[i] <= 0:
            slopes.append(0.0)  # local extremum -> flatten to avoid overshoot
        else:
            slopes.append((secant[i - 1] + secant[i]) / 2)
    slopes.append(secant[-1])
    return slopes


def _interpolate(coarse: Series, step_min: int) -> Series:
    if len(coarse) < 2:
        return list(coarse)
    slopes = _monotone_slopes(coarse)
    step = step_min * 60
    out: Series = []
    start, end = coarse[0][0], coarse[-1][0]
    t = start
    seg = 0
    while t <= end:
        while seg < len(coarse) - 2 and t > coarse[seg + 1][0]:
            seg += 1
        (t0, v0), (t1, v1) = coarse[seg], coarse[seg + 1]
        val = _pchip_like(t0, t1, v0, v1, slopes[seg], slopes[seg + 1], t)
        out.append((t, max(0.0, val)))
        t += step
    return out


def refine(coarse: Series, wind: Series | None = None,
           horizon_min: int = NOWCAST_HORIZON_MIN, step_min: int = NOWCAST_STEP_MIN) -> Series:
    """Refine a coarse forecast to `step_min` resolution.

    Uses the METOC Lagrangian nowcast when enabled and implemented, else a
    shape-preserving interpolation fallback.
    """
    if not coarse:
        return []
    if USE_METOC:
        try:
            return lagrangian_nowcast(coarse, wind, horizon_min, step_min)
        except NotImplementedError:
            pass  # fall through to interpolation
    return _interpolate(coarse, step_min)


def provider() -> str:
    return "metoc-lagrangian" if USE_METOC else "interpolation-fallback"


# Allow callers to inject an implementation at runtime without editing this file.
def register(fn: Callable[[Series, "Series | None", int, int], Series]) -> None:
    global lagrangian_nowcast, USE_METOC  # noqa: PLW0603
    lagrangian_nowcast = fn  # type: ignore[assignment]
    USE_METOC = True
