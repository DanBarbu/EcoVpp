"""Solar yield forecaster.

Pulls a 24h global tilted irradiance forecast from Open-Meteo, converts to a
DC yield (kW) using panel rating + system efficiency, and uploads the series
to FlexMeasures using the v0.31 forecast trigger API:

  POST /api/v3_0/sensors/<id>/forecasts/trigger
  GET  /api/v3_0/sensors/<id>/forecasts/<job_uuid>

Run as a CronJob (every 60 minutes).
"""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone

import httpx

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("forecast")

LAT = float(os.getenv("SITE_LAT", "44.4268"))  # default: Bucharest
LON = float(os.getenv("SITE_LON", "26.1025"))
TILT = float(os.getenv("PANEL_TILT", "30"))
AZIMUTH = float(os.getenv("PANEL_AZIMUTH", "180"))
PANEL_KWP = float(os.getenv("PANEL_KWP", "5.0"))
SYSTEM_EFFICIENCY = float(os.getenv("SYSTEM_EFFICIENCY", "0.85"))

FLEXMEASURES_URL = os.getenv("FLEXMEASURES_URL", "http://flexmeasures:5000")
FLEXMEASURES_TOKEN = os.getenv("FLEXMEASURES_TOKEN", "")
SENSOR_ID = int(os.getenv("FLEXMEASURES_FORECAST_SENSOR_ID", "2"))


def fetch_irradiance() -> tuple[list[str], list[float]]:
    params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": "global_tilted_irradiance",
        "tilt": TILT,
        "azimuth": AZIMUTH,
        "forecast_days": 1,
        "timezone": "UTC",
    }
    resp = httpx.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10.0)
    resp.raise_for_status()
    data = resp.json()["hourly"]
    return data["time"], data["global_tilted_irradiance"]


def to_kw(gti_w_m2: list[float]) -> list[float]:
    # 1 kWp ~ 1 kW at 1000 W/m² standard test conditions.
    return [round(PANEL_KWP * (gti / 1000.0) * SYSTEM_EFFICIENCY, 3) for gti in gti_w_m2]


def upload_to_flexmeasures(times: list[str], kw: list[float]) -> str:
    if not FLEXMEASURES_TOKEN:
        log.warning("FLEXMEASURES_TOKEN not set — printing forecast and exiting")
        for t, v in zip(times, kw):
            log.info("%s -> %s kW", t, v)
        return "dry-run"

    payload = {
        "values": kw,
        "start": times[0],
        "duration": "PT24H",
        "unit": "kW",
    }
    headers = {"Authorization": f"Bearer {FLEXMEASURES_TOKEN}"}
    trigger = httpx.post(
        f"{FLEXMEASURES_URL}/api/v3_0/sensors/{SENSOR_ID}/forecasts/trigger",
        json=payload,
        headers=headers,
        timeout=15.0,
    )
    trigger.raise_for_status()
    job_uuid = trigger.json().get("job_uuid")
    log.info("triggered forecast job %s", job_uuid)

    deadline = time.time() + 60
    while time.time() < deadline:
        status = httpx.get(
            f"{FLEXMEASURES_URL}/api/v3_0/sensors/{SENSOR_ID}/forecasts/{job_uuid}",
            headers=headers,
            timeout=10.0,
        )
        if status.status_code == 200 and status.json().get("status") == "complete":
            log.info("forecast complete")
            return job_uuid or "ok"
        time.sleep(2)
    raise RuntimeError("forecast job did not complete in time")


def main() -> int:
    log.info("forecast run @ %s for (%.4f,%.4f) tilt=%s az=%s", datetime.now(tz=timezone.utc), LAT, LON, TILT, AZIMUTH)
    try:
        times, gti = fetch_irradiance()
        kw = to_kw(gti)
        upload_to_flexmeasures(times, kw)
    except Exception as exc:  # noqa: BLE001
        log.exception("forecast failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
