"""Weather acquisition for the price forecaster.

Pulls coarse forecasts from Open-Meteo (15-minutely where available, else
hourly) and refines them to 10-minute resolution via the METOC nowcast
adapter. Returns aligned 10-minute series for the variables the price model
needs: global tilted irradiance (PV proxy), wind speed (wind proxy), and
2 m temperature (demand proxy).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

import metoc_nowcast

LAT = float(os.getenv("SITE_LAT", "44.4268"))
LON = float(os.getenv("SITE_LON", "26.1025"))
PANEL_TILT = float(os.getenv("PANEL_TILT", "30"))
PANEL_AZIMUTH = float(os.getenv("PANEL_AZIMUTH", "180"))
STEP_MIN = int(os.getenv("NOWCAST_STEP_MIN", "10"))

Series = list[tuple[int, float]]


@dataclass
class WeatherForecast:
    gti: Series          # W/m²  (global tilted irradiance)
    wind: Series         # m/s   (10 m wind speed)
    temperature: Series  # °C    (2 m temperature)
    resolution_min: int
    provider: str

    def horizon_hours(self) -> float:
        if not self.gti:
            return 0.0
        return (self.gti[-1][0] - self.gti[0][0]) / 3600.0


def _to_series(times: list[str], values: list[float | None]) -> Series:
    out: Series = []
    for t, v in zip(times, values):
        if v is None:
            continue
        ts = int(datetime.fromisoformat(t).replace(tzinfo=timezone.utc).timestamp())
        out.append((ts, float(v)))
    return out


def fetch(horizon_hours: int = 6, client: httpx.Client | None = None,
          lat: float | None = None, lon: float | None = None) -> WeatherForecast:
    owned = client is None
    client = client or httpx.Client(timeout=10.0)
    try:
        params = {
            "latitude": LAT if lat is None else lat,
            "longitude": LON if lon is None else lon,
            "minutely_15": "global_tilted_irradiance,wind_speed_10m,temperature_2m",
            "tilt": PANEL_TILT,
            "azimuth": PANEL_AZIMUTH,
            "forecast_hours": horizon_hours,
            "timezone": "UTC",
        }
        resp = client.get("https://api.open-meteo.com/v1/forecast", params=params)
        resp.raise_for_status()
        data = resp.json()
        block = data.get("minutely_15") or data.get("hourly") or {}
        times = block.get("time", [])
        gti = _to_series(times, block.get("global_tilted_irradiance", []))
        wind = _to_series(times, block.get("wind_speed_10m", []))
        temp = _to_series(times, block.get("temperature_2m", []))
    finally:
        if owned:
            client.close()

    gti_r = metoc_nowcast.refine(gti, wind=wind, step_min=STEP_MIN)
    wind_r = metoc_nowcast.refine(wind, wind=wind, step_min=STEP_MIN)
    temp_r = metoc_nowcast.refine(temp, wind=wind, step_min=STEP_MIN)

    return WeatherForecast(
        gti=gti_r,
        wind=wind_r,
        temperature=temp_r,
        resolution_min=STEP_MIN,
        provider=metoc_nowcast.provider(),
    )
