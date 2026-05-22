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

## Test

```bash
cd services/price-forecast && PYTHONPATH=. pytest -q tests
```
