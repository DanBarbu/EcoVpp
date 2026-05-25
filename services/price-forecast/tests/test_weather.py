from __future__ import annotations

import importlib


def test_weather_module_exposes_archive():
    w = importlib.import_module("weather")
    assert hasattr(w, "archive"), "weather.archive() must exist for historical backtests"
    # Signature sanity: archive(start, end, lat=, lon=, client=)
    import inspect
    sig = inspect.signature(w.archive)
    assert {"start", "end", "lat", "lon", "client"} <= set(sig.parameters)


def test_to_series_drops_nulls_and_sorts():
    w = importlib.import_module("weather")
    # _to_series is an internal helper used by both fetch() and archive().
    times = ["2026-01-01T00:00", "2026-01-01T01:00", "2026-01-01T02:00"]
    vals = [100.0, None, 200.0]
    out = w._to_series(times, vals)
    assert len(out) == 2
    assert [v for _, v in out] == [100.0, 200.0]
    assert out[1][0] - out[0][0] == 7200  # second valid point is +2h
