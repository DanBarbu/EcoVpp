# price-forecast

Weather-driven electricity price forecaster. Publishes a **10-minute-resolution**
price curve that the `flexibility-engine` consumes (in priority over FlexMeasures
and the synthetic dev fallback) and the dashboard renders as a panel.

## Pipeline

```
Open-Meteo (15-min NWP)  ──►  metoc_nowcast.refine()  ──►  model.price_curve()  ──►  /api/v1/price/*
   GTI · wind · temp          10-min Lagrangian nowcast      residual-load merit order
```

- `weather.py` — pulls `global_tilted_irradiance`, `wind_speed_10m`, `temperature_2m`
  from Open-Meteo and refines each to 10-min steps via the nowcast adapter.
- `metoc_nowcast.py` — **integration seam for the METOC Lagrangian platform**
  (branch `claude/metoc-lagrangian-platform-XYLxL`). Implement
  `lagrangian_nowcast()` or call `register(fn)` at runtime to plug in the real
  advection nowcast. Until then a shape-preserving interpolation fallback runs so
  the pipeline is exercisable end-to-end.
- `model.py` — transparent residual-load merit-order price model. Every
  coefficient is an env var for per-bidding-zone calibration.
- `price_forecast.py` — FastAPI service.

## Wiring in the METOC nowcast

Two options:

1. **Edit the adapter.** Implement `lagrangian_nowcast(coarse, wind, horizon_min, step_min)`
   in `metoc_nowcast.py` using the METOC platform's advection routines, and set
   `METOC_NOWCAST=1`.

2. **Register at runtime** (no edit to this file):

   ```python
   import metoc_nowcast
   from metoc.lagrangian import advect_field  # the METOC package
   metoc_nowcast.register(lambda coarse, wind, h, s: advect_field(coarse, wind, h, s))
   ```

The contract is a list of `(epoch_seconds, value)` points in native units.

## Endpoints

| Method | Path | Returns |
|--------|------|---------|
| GET | `/api/v1/price/forecast` | full 10-min curve |
| GET | `/api/v1/price/current` | nearest point to now |
| GET | `/api/v1/price/next?minutes=10` | point N minutes ahead |
| GET | `/healthz`, `/metrics` | health / Prometheus |

## Key env vars

| Var | Default | Meaning |
|-----|---------|---------|
| `METOC_NOWCAST` | `0` | `1` to use the METOC Lagrangian nowcast |
| `NOWCAST_STEP_MIN` | `10` | output resolution (minutes) |
| `PRICE_HORIZON_HOURS` | `6` | forecast horizon |
| `SITE_LAT`/`SITE_LON` | Bucharest | site coordinates |
| `PV_CAPACITY_KW`/`WIND_CAPACITY_KW` | 5000 / 2000 | installed renewable capacity |
| `PRICE_*` | see `model.py` | merit-order curve calibration |

## Correlation check & calibration against real market prices

The pure-weather merit-order model is a baseline; real day-ahead prices (gas
coupling, hydro, nuclear, cross-border flows) won't correlate strongly with it.
`validate.py` measures the Pearson correlation against the real market price and
adjusts the algorithm when it's below 90%.

### Token-free (default) — Energy-Charts / Fraunhofer ISE

No registration, no token, no secret. The default `--source energycharts` uses
the public `https://api.energy-charts.info/price` API:

```bash
python validate.py --zone RO --days 14       # Romania, token-free
python validate.py --all --days 14           # every EU zone, token-free
```

### Optional — ENTSO-E (official source, needs a token)

```bash
export ENTSOE_TOKEN=xxxxxxxx                 # https://transparency.entsoe.eu
python validate.py --all --days 14 --source entsoe
# Romania also accepts a manual OPCOM PZU export:
OPCOM_CSV=opcom_pzu.csv python validate.py --zone RO --source entsoe
```

### What the calibration does (same for every country)

- **r ≥ 0.90** → keeps the merit-order model, refits its level (`p_zero`,
  `slope`) to the market, writes `calibration.<zone>.json` mode `merit_order`.
- **r < 0.90** → writes mode `anchored`: the service then uses
  `price_curve_anchored()`, where the **hourly day-ahead baseline IS the real
  market price** and the weather/METOC nowcast only shapes it to 10-minute
  resolution. The forecast tracks the market by construction while keeping
  sub-hourly value. Refit merit-order coefficients remain as the offline
  fallback beyond the day-ahead horizon.

`zones.py` lists EU-27 principal bidding zones with both an Energy-Charts code
(`ec`, token-free source) and an ENTSO-E EIC (`eic`, official source). Isolated
islands (CY, MT) have no Energy-Charts coupling and need `--source entsoe`.
`model.py` and the service auto-load the per-zone calibration.

`--all` writes one `calibration.<ZONE>.json` per zone (under `CALIBRATION_DIR`,
default `calibrations/`) and prints a per-zone correlation table plus a summary
of how many zones fell below threshold and were anchored to their market price.

Because Pearson correlation is scale-invariant and the OLS step absorbs linear
capacity scaling, the same default merit-order model is correlated against each
market without per-country capacity tuning — the **anchoring** is what lifts
correlation, identically for every country.

A service instance serves one zone via `ZONE` (e.g. `ZONE=ES`): it loads that
zone's calibration, pulls weather at the zone centroid, and anchors to that
zone's market when calibrated to do so.

### Weekly auto-recalibration

`.github/workflows/price-calibration.yml` runs `validate.py --all` every Monday
(and on demand) and commits the refreshed `calibration.<ZONE>.json` files back
to the repo. It uses the **token-free Energy-Charts source by default — no
secret required**, so it works the moment Actions is enabled. Set the dispatch
input `source=entsoe` (with an `ENTSOE_TOKEN` secret) to use the official feed.

### Key calibration env vars

| Var | Default | Meaning |
|-----|---------|---------|
| `PRICE_SOURCE` | `energycharts` | market source for anchoring: `energycharts` (token-free) or `entsoe` |
| `ENTSOE_TOKEN` | — | ENTSO-E API token (only for `PRICE_SOURCE=entsoe`) |
| `ZONE` | — | EU bidding zone this service instance serves (see `zones.py`) |
| `OPCOM_CSV` | — | RO-only `timestamp,price_eur_mwh` CSV fallback |
| `CORRELATION_THRESHOLD` | `0.90` | switch to anchored mode below this |
| `CALIBRATION_DIR` | `.` | directory holding `calibration.<zone>.json` files |
| `CALIBRATION_FILE` | `calibration.json` | default (zone-less) calibration path |

> Note: a live correlation run needs outbound network (Energy-Charts is
> token-free), so it runs on your machine, in the cluster, or in the scheduled
> workflow — not in a no-egress build sandbox.

## Test

```bash
cd services/price-forecast && PYTHONPATH=. pytest -q tests
```
