# ECO-VPP Architecture

```
                     ┌────────────────────────────────────────────────────┐
                     │                 Energy Community                    │
                     │ ┌──────────┐  ┌──────────┐  ┌──────────┐           │
                     │ │ Apt #1   │  │ Apt #N   │  │ Rooftop  │           │
                     │ │ ESP32-S3 │  │ ESP32-S3 │  │ Inverter │           │
                     │ └────┬─────┘  └────┬─────┘  └────┬─────┘           │
                     │      │ HaLow Wi-Fi (802.11ah)   │                   │
                     │      ▼             ▼            ▼                   │
                     │             ┌──────────────┐                        │
                     │             │ HaLow Gateway │                       │
                     │             └──────┬───────┘                        │
                     └────────────────────┼────────────────────────────────┘
                                          │ MQTT / HTTPS
                                          ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │                          Cloud / Kubernetes                            │
   │                                                                        │
   │  Mainflux IoT  ──webhook──►  webhook-receiver  ──►  PostgreSQL+PostGIS │
   │                                  │  ▲                       ▲         │
   │                                  │  │                       │         │
   │                                  │  └── WebSocket ──────────┘         │
   │                                  ▼                                     │
   │  RED II Allocator  ──shares──► energy_shares ──► Settlement (EW Origin)│
   │                                                                        │
   │  FlexMeasures (forecast + price) ──► Flexibility Engine ──► MQTT cmds  │
   │                                                                        │
   │              GSY-e P2P Market  ◄─── surplus offers                     │
   │              Energy Web DID    ◄─── identity & GoO NFTs                │
   │              Dashboard (React) ◄─── REST + WebSocket                   │
   └──────────────────────────────────────────────────────────────────────┘
```

## Component map

| Component | Role | Doc anchor |
|-----------|------|-----------|
| `webhook-receiver` | Telemetry ingest, asset registry, share/incentive APIs, dashboard WS hub | Sprint 0–1 |
| `red-ii-allocator` | Pro-rata Collective Self-Consumption sharing | Sprint 2 |
| `flexibility-engine` | Price-driven `SET_LOAD_LIMIT` issuance over MQTT | Sprint 3 |
| `forecast` | 24h GTI → DC kW forecast pushed to FlexMeasures | Sprint 3 |
| `settlement` | Batch hash anchoring on Energy Web Origin, GoO certificates | Sprint 4 |
| `dashboard` | Operator + resident view (live shares, incentives) | Sprint 0–4 |

## Latency targets

* HaLow ingest → DB: < 5 s (HaLow itself can be 2–3 s)
* Cloud price tick → SET_LOAD_LIMIT at edge: **< 3 s** (Sprint 3 acceptance)
* Settlement batch: ≤ 60 s
