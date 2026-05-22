from __future__ import annotations

import importlib


def test_refine_upsamples_to_step():
    nc = importlib.import_module("metoc_nowcast")
    # Two hourly points → 10-min steps should yield ~7 points (0,10,...,60).
    coarse = [(0, 0.0), (3600, 600.0)]
    out = nc.refine(coarse, step_min=10)
    assert len(out) == 7
    assert out[0][0] == 0 and out[-1][0] == 3600
    # Monotone-increasing input stays non-negative and bounded by endpoints.
    assert all(0.0 <= v <= 600.0 + 1e-6 for _, v in out)


def test_refine_handles_short_series():
    nc = importlib.import_module("metoc_nowcast")
    assert nc.refine([]) == []
    assert nc.refine([(0, 5.0)]) == [(0, 5.0)]


def test_register_swaps_implementation():
    nc = importlib.import_module("metoc_nowcast")
    sentinel = [(0, 42.0)]
    nc.register(lambda coarse, wind, h, s: sentinel)
    try:
        assert nc.refine([(0, 1.0), (60, 2.0)], step_min=10) == sentinel
        assert nc.provider() == "metoc-lagrangian"
    finally:
        # restore fallback so other tests are unaffected
        nc.USE_METOC = False
