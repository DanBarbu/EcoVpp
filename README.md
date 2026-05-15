# ECO-VPP — Energy Community Orchestrated Virtual Power Plant

White-label, full-stack orchestration platform that lets a multi-unit
condominium operate as a **single Virtual Power Plant**, optimising
**RED II Collective Self-Consumption** and participating in **Local
Flexibility Markets** via the **GSY-e P2P market**.

Target call: **HORIZON-CL5-2026-02-D3-20** • TRL-7
Hardware target: sub-€20 ESP32-S3 + ADE7913 + HaLow Wi-Fi node

---

## What's in the box

```
.
├── services/
│   ├── webhook-receiver/      # FastAPI ingest, asset registry, dashboard WS hub
│   ├── flexibility-engine/    # FlexMeasures → MQTT SET_LOAD_LIMIT issuer
│   ├── red-ii-allocator/      # RED II pro-rata Collective Self-Consumption
│   ├── settlement/            # Energy Web Origin batch anchoring + GoO certs
│   └── forecast/              # Open-Meteo → FlexMeasures solar forecast (CronJob)
├── dashboard/                 # React + Vite operator dashboard
├── helm/eco-vpp/              # Production Helm chart (postgres, ingress, HPA, …)
├── docker-compose.yml         # One-command local stack
├── .github/workflows/ci-cd.yml# Lint, test, build, scan, publish, deploy
└── docs/architecture.md
```

A live architecture diagram lives in [docs/architecture.md](docs/architecture.md).

## Quick start (local)

Prerequisites: Docker, Docker Compose, ports 3000 / 8000–8002 / 5432 / 1883 free.

```bash
git clone https://github.com/DanBarbu/EcoVpp.git
cd EcoVpp
docker compose up --build -d
```

Once everything is healthy:

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:3000 |
| Webhook receiver | http://localhost:8000/healthz |
| Flexibility engine metrics | http://localhost:8001/metrics |
| Settlement | http://localhost:8002/healthz |
| Mosquitto MQTT (Mainflux stand-in) | tcp://localhost:1883 |

Register an apartment meter and post a sample telemetry record:

```bash
curl -s http://localhost:8000/api/v1/assets -H 'Content-Type: application/json' \
  -d '{"did":"did:ethr:volta:0x111","asset_type":"meter","location":"Apt 1","capacity_kw":3.5}'

curl -s http://localhost:8000/api/v1/telemetry/ingest \
  -H 'Content-Type: application/json' -H 'X-Ingest-Token: dev-token' \
  -d '{"did":"did:ethr:volta:0x111","voltage":230.1,"current":1.42,"power_w":326.7,"energy_kwh":0.054,"confidence":0.96}'
```

The dashboard auto-refreshes every 30 s and receives live curtailment
incentives over WebSocket.

## CI/CD

`.github/workflows/ci-cd.yml`:

1. Lints and renders the Helm chart (`values.yaml` + `values.production.yaml`).
2. Compiles & lints every Python service (matrix).
3. Builds and pushes one image per service to **GHCR** (`ghcr.io/<owner>/ecovpp/<svc>`).
4. Scans every image with **Trivy** (Critical/High).
5. On version tags, packages and `helm push`-es the chart as an OCI artifact.
6. On `main`, runs `helm upgrade --install` against the cluster pointed at
   by the **`KUBECONFIG_PROD`** secret (base64-encoded kubeconfig).

### Required GitHub secrets

| Secret | What |
|--------|------|
| `KUBECONFIG_PROD` | Base64-encoded kubeconfig (`cat ~/.kube/config \| base64 -w0`) |

`GITHUB_TOKEN` is provided automatically and is used to push to GHCR.

## Production deploy with Helm

```bash
helm upgrade --install eco-vpp helm/eco-vpp \
  --namespace eco-vpp --create-namespace \
  -f helm/eco-vpp/values.production.yaml \
  --set image.tag=$(git rev-parse --short=7 HEAD)
```

Values you'll likely override:

```yaml
ingestToken: "rotate-me"
flexmeasures: { token: "<flexmeasures-api-token>" }
settlement:   { dryRun: false, originContract: "0x...", privateKey: "<sealed>" }
ingress:      { enabled: true, host: eco-vpp.energy, tls: { enabled: true, secretName: eco-vpp-tls } }
```

## Sub-€20 hardware node (ESP32-S3)

The MicroPython firmware ships as a Helm `ConfigMap` so you can pull a
device-ready `main.py` straight from the cluster:

```bash
kubectl -n eco-vpp get configmap eco-vpp-esp32-code \
  -o jsonpath='{.data.main\.py}' > main.py
ampy --port /dev/ttyUSB0 put main.py
```

Per-device parameters (`WIFI_SSID`, `WIFI_PASS`, `MQTT_BROKER`, `DEVICE_DID`,
`INGEST_TOKEN`) are templated from `values.yaml` and can be overridden per-site.

The firmware:
* reads V/I/P/E from the ADE7913 over SPI,
* runs analog-meter OCR (AI-on-the-edge-device build) when configured,
* posts samples with exponential back-off (HaLow tolerates seconds of latency),
* honours a **local manual override** (RED II grid-safety requirement).

## RED II sharing

`red-ii-allocator` wakes every 15 min, sums inverter production and meter
consumption over the window, allocates surplus solar **pro-rata** across
consumers (writing rows into `energy_shares` priced at the internal tariff),
and pushes any leftover surplus to the **GSY-e P2P market** as an offer.

## Settlement & GDPR

`settlement` periodically batches unsettled `energy_shares`, computes a SHA-256
digest of the batch, and anchors it on **Energy Web Origin**. PII never leaves
the relational DB — only DIDs and kWh deltas reach the chain. GoO NFTs are
mintable per asset+batch via `/api/v1/certificates`. Set
`settlement.dryRun=false` in values to enable on-chain writes.

## FlexMeasures forecasting

The `forecast` CronJob (default: every hour at +5 min) pulls a 24-hour
`global_tilted_irradiance` series from Open-Meteo, converts it to DC kW with
the configured panel rating + system efficiency, and uploads it to
FlexMeasures via the v0.31 forecast API:

```
POST /api/v3_0/sensors/<id>/forecasts/trigger
GET  /api/v3_0/sensors/<id>/forecasts/<job_uuid>
```

## Security & compliance

* **Auth** — `INGEST_TOKEN` header on all ingest paths; rotate via the
  `eco-vpp-secrets` Kubernetes Secret.
* **Container scanning** — Trivy gates every image build.
* **Tenancy** — namespace isolation in K8s; per-tenant DIDs in PostgreSQL.
* **Privacy** — only DIDs + kWh on-chain; ZK-proof masking hooks live in
  `services/settlement` (`/api/v1/proof/{tx_hash}` returns a Merkle-tree
  proof without leaking PII).
* **Grid safety** — every node firmware honours a local manual override
  (RED II / IEMD requirement).
* **Audit** — `energy_shares.settlement_tx` gives an immutable trail
  consumable by MiCA-compliant reporting tooling.

## Roadmap

The 6-sprint plan lives in the original [Master Technical Annex](docs/architecture.md):
Sprint 0 (handshake) → 1 (edge AI / OCR) → 2 (RED II) → **3 (VPP dispatch)** →
4 (blockchain settlement) → 5 (chaos / scale).

## License

Apache 2.0 — see [LICENSE](LICENSE).

---

*Built for the Horizon Europe Clean Energy Transition call.*
