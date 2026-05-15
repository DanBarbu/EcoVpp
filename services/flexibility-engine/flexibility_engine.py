"""ECO-VPP Flexibility Engine.

Polls FlexMeasures for the latest grid congestion / price signal, computes a
SET_LOAD_LIMIT for shiftable loads (EVs, heaters), and:

  1. Publishes the limit over MQTT to HaLow gateways (Mainflux topic).
  2. Pushes the resulting incentive to the webhook-receiver, which fans it out
     to dashboards via WebSocket.

Target end-to-end latency: < 3 s (Sprint 3 acceptance criterion).
"""
from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
import paho.mqtt.client as mqtt
from prometheus_client import Counter, Gauge, start_http_server

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("flex-engine")

FLEXMEASURES_URL = os.getenv("FLEXMEASURES_URL", "http://flexmeasures:5000")
FLEXMEASURES_TOKEN = os.getenv("FLEXMEASURES_TOKEN", "")
FLEXMEASURES_SENSOR_ID = int(os.getenv("FLEXMEASURES_SENSOR_ID", "1"))

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://webhook-receiver:8000")
INGEST_TOKEN = os.getenv("INGEST_TOKEN", "dev-token")

MQTT_HOST = os.getenv("MQTT_HOST", "mainflux-mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_LOAD_TOPIC", "ecovpp/commands/load_limit")

POLL_INTERVAL_S = float(os.getenv("POLL_INTERVAL_S", "5"))
METRICS_PORT = int(os.getenv("METRICS_PORT", "8001"))

# Price thresholds in EUR/MWh that map to curtailment levels.
PRICE_LOW = float(os.getenv("PRICE_LOW", "40"))
PRICE_HIGH = float(os.getenv("PRICE_HIGH", "200"))

CMD_COUNTER = Counter("ecovpp_load_commands_total", "Load-limit commands sent")
CURRENT_SIGNAL = Gauge("ecovpp_grid_signal", "Current curtailment signal [0..1]")
CURRENT_PRICE = Gauge("ecovpp_grid_price_eur_mwh", "Current grid price (EUR/MWh)")
LOOP_LATENCY = Gauge("ecovpp_flex_loop_seconds", "Latest loop wall-clock latency")


@dataclass
class GridSignal:
    price_eur_mwh: float
    timestamp: datetime

    @property
    def curtailment(self) -> float:
        if self.price_eur_mwh <= PRICE_LOW:
            return 0.0
        if self.price_eur_mwh >= PRICE_HIGH:
            return 1.0
        return (self.price_eur_mwh - PRICE_LOW) / (PRICE_HIGH - PRICE_LOW)


def fetch_signal(client: httpx.Client) -> GridSignal | None:
    """Pull the latest beliefs from FlexMeasures.

    Falls back to a synthetic sinusoid in dev mode (no token configured) so the
    full pipeline stays exercisable without a live FlexMeasures install.
    """
    if not FLEXMEASURES_TOKEN:
        # Dev fallback: oscillate between 30 and 220 EUR/MWh on a 10-minute cycle.
        now = datetime.now(tz=timezone.utc)
        phase = (now.minute * 60 + now.second) / 600.0
        import math

        price = 125 + 95 * math.sin(2 * math.pi * phase)
        return GridSignal(price_eur_mwh=price, timestamp=now)

    try:
        resp = client.get(
            f"{FLEXMEASURES_URL}/api/v3_0/sensors/{FLEXMEASURES_SENSOR_ID}/data",
            headers={"Authorization": f"Bearer {FLEXMEASURES_TOKEN}"},
            params={"resolution": "PT15M", "horizon": "PT0H"},
            timeout=4.0,
        )
        resp.raise_for_status()
        data = resp.json()
        values = data.get("values") or []
        if not values:
            return None
        price = float(values[-1])
        ts = datetime.fromisoformat(data.get("start", datetime.now(timezone.utc).isoformat()))
        return GridSignal(price_eur_mwh=price, timestamp=ts)
    except Exception as exc:  # noqa: BLE001
        log.warning("FlexMeasures fetch failed: %s", exc)
        return None


def build_command(signal: GridSignal) -> dict[str, Any]:
    curtail = signal.curtailment
    return {
        "command": "SET_LOAD_LIMIT",
        "limit_pct": round((1.0 - curtail) * 100, 1),
        "price_eur_kwh": round(signal.price_eur_mwh / 1000.0, 4),
        "signal": round(curtail, 3),
        "issued_at": datetime.now(tz=timezone.utc).isoformat(),
    }


class Publisher:
    def __init__(self) -> None:
        self.mqtt = mqtt.Client(client_id="ecovpp-flex-engine", protocol=mqtt.MQTTv311)
        self.mqtt.enable_logger(log)
        self._connected = threading.Event()
        self.mqtt.on_connect = self._on_connect

    def _on_connect(self, _client, _userdata, _flags, rc, *_):  # noqa: ANN001
        if rc == 0:
            self._connected.set()
            log.info("MQTT connected")
        else:
            log.error("MQTT connect failed rc=%s", rc)

    def start(self) -> None:
        try:
            self.mqtt.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            self.mqtt.loop_start()
        except Exception as exc:  # noqa: BLE001
            log.warning("MQTT unavailable (%s); commands will only be pushed via HTTP", exc)

    def stop(self) -> None:
        self.mqtt.loop_stop()
        self.mqtt.disconnect()

    def publish_mqtt(self, payload: dict[str, Any]) -> None:
        if not self._connected.is_set():
            return
        self.mqtt.publish(MQTT_TOPIC, json.dumps(payload), qos=1)

    def push_to_webhook(self, http: httpx.Client, payload: dict[str, Any]) -> None:
        try:
            http.post(
                f"{WEBHOOK_URL}/api/internal/incentive",
                json={"price": payload["price_eur_kwh"], "signal": payload["signal"], "limit_pct": payload["limit_pct"]},
                timeout=2.0,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("dashboard fan-out failed: %s", exc)


def run() -> None:
    start_http_server(METRICS_PORT)
    log.info("metrics on :%s, polling FlexMeasures every %.1fs", METRICS_PORT, POLL_INTERVAL_S)

    publisher = Publisher()
    publisher.start()

    stop = threading.Event()

    def _graceful(*_: Any) -> None:
        log.info("shutting down")
        stop.set()

    signal.signal(signal.SIGTERM, _graceful)
    signal.signal(signal.SIGINT, _graceful)

    with httpx.Client() as http:
        while not stop.is_set():
            t0 = time.monotonic()
            sig = fetch_signal(http)
            if sig:
                cmd = build_command(sig)
                CURRENT_SIGNAL.set(sig.curtailment)
                CURRENT_PRICE.set(sig.price_eur_mwh)
                publisher.publish_mqtt(cmd)
                publisher.push_to_webhook(http, cmd)
                CMD_COUNTER.inc()
                log.info("issued %s", cmd)
            LOOP_LATENCY.set(time.monotonic() - t0)
            stop.wait(POLL_INTERVAL_S)

    publisher.stop()


if __name__ == "__main__":
    run()
