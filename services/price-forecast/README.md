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

## Correlation check & calibration against OPCOM (Romania)

The pure-weather merit-order model is a baseline; real RO day-ahead prices
(gas coupling, hydro, Cernavodă nuclear, RO–HU/BG/RS cross-border flows) won't
correlate strongly with it. `validate.py` measures the correlation against OPCOM
and adjusts the algorithm when it's below 90%.

```bash
# free token from https://transparency.entsoe.eu (My Account → API access)
export ENTSOE_TOKEN=xxxxxxxx
python validate.py --days 14
# …or use a manually exported OPCOM PZU report:
OPCOM_CSV=opcom_pzu.csv python validate.py --days 14
```

- **r ≥ 0.90** → keeps the merit-order model, refits its level (`p_zero`,
  `slope`) to OPCOM, writes `calibration.json` with `mode: merit_order`.
- **r < 0.90** → writes `mode: anchored`: the service then uses
  `price_curve_anchored()`, where the **hourly day-ahead baseline is OPCOM** and
  the weather/METOC nowcast only shapes it to 10-minute resolution. This makes
  the delivered forecast track OPCOM by construction while keeping sub-hourly
  value. The refit merit-order coefficients remain as the offline fallback for
  real-time beyond the day-ahead horizon.

`model.py` and the service load `calibration.json` automatically (path via
`CALIBRATION_FILE`). Data source: **ENTSO-E Transparency Platform**, document
type A44, RO bidding zone `10YRO-TEL------P` — the canonical machine-readable
carrier of the OPCOM day-ahead price. The OPCOM website itself has no clean
public API, hence ENTSO-E (or a manual CSV) as the source.

### All EU bidding zones

The same machinery works for every EU day-ahead market — ENTSO-E carries them
all. `zones.py` lists the EU-27 principal bidding zones (EIC + weather centroid).

```bash
export ENTSOE_TOKEN=xxxxxxxx
python validate.py --zone DE_LU --days 14   # one zone
python validate.py --all --days 14          # every EU zone
```

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
(and on demand), then commits the refreshed `calibration.<ZONE>.json` files back
to the repo. Add the repo secret **`ENTSOE_TOKEN`** to enable it; without the
secret the job no-ops.

### Key calibration env vars

| Var | Default | Meaning |
|-----|---------|---------|
| `ENTSOE_TOKEN` | — | ENTSO-E API token (required for live fetch, all zones) |
| `ZONE` | — | EU bidding zone this service instance serves (see `zones.py`) |
| `OPCOM_CSV` | — | RO-only `timestamp,price_eur_mwh` CSV fallback |
| `CORRELATION_THRESHOLD` | `0.90` | switch to anchored mode below this |
| `CALIBRATION_DIR` | `.` | directory holding `calibration.<zone>.json` files |
| `CALIBRATION_FILE` | `calibration.json` | default (zone-less) calibration path |

> Note: a live correlation run needs outbound network + the ENTSO-E token, so it
> must run on your machine, in the cluster, or in the scheduled workflow — not in
> a no-egress build sandbox.

## Test

```bash
cd services/price-forecast && PYTHONPATH=. pytest -q tests
```
