from __future__ import annotations

import importlib
import math


def test_pearson_perfect_and_zero():
    cal = importlib.import_module("calibration")
    assert abs(cal.pearson([1, 2, 3, 4], [2, 4, 6, 8]) - 1.0) < 1e-9
    assert abs(cal.pearson([1, 2, 3, 4], [4, 3, 2, 1]) + 1.0) < 1e-9
    # constant series → undefined → 0
    assert cal.pearson([1, 1, 1], [1, 2, 3]) == 0.0


def test_ols_recovers_line():
    cal = importlib.import_module("calibration")
    x = list(range(10))
    y = [3 * xi + 7 for xi in x]
    slope, intercept = cal.ols(x, y)
    assert abs(slope - 3) < 1e-9 and abs(intercept - 7) < 1e-9


def test_align_buckets_to_hours():
    cal = importlib.import_module("calibration")
    # two 10-min model points in hour 0, one OPCOM hourly point at hour 0
    model = [(0, 50.0), (600, 70.0)]
    opcom = [(0, 100.0)]
    a, b, hours = cal.align(model, opcom)
    assert hours == [0]
    assert a == [60.0]  # mean of 50,70
    assert b == [100.0]


def test_evaluate_selects_anchored_when_uncorrelated():
    cal = importlib.import_module("calibration")
    # model anti-correlated with opcom over 6 hours → r < 0.90 → anchored
    model = [(h * 3600, float(h)) for h in range(6)]
    opcom = [(h * 3600, float(5 - h)) for h in range(6)]
    c = cal.evaluate(model, opcom, threshold=0.90)
    assert c.mode == "anchored"
    assert c.correlation < 0.90


def test_evaluate_keeps_merit_order_when_correlated():
    cal = importlib.import_module("calibration")
    model = [(h * 3600, 40 + 5 * h) for h in range(8)]
    opcom = [(h * 3600, 80 + 9 * h + (1 if h % 2 else -1)) for h in range(8)]
    c = cal.evaluate(model, opcom, threshold=0.90)
    assert c.mode == "merit_order"
    assert c.correlation >= 0.90


def test_anchored_curve_tracks_opcom_hourly():
    m = importlib.import_module("model")
    # One hour of OPCOM at 150 EUR/MWh; flat weather → anchored price ≈ 150.
    hour = 1_700_000_000 - (1_700_000_000 % 3600)
    opcom = [(hour, 150.0)]
    gti = [(hour, 0.0), (hour + 600, 0.0)]
    wind = [(hour, 0.0), (hour + 600, 0.0)]
    temp = [(hour, 10.0), (hour + 600, 10.0)]
    pts = m.price_curve_anchored(opcom, gti, wind, temp)
    assert pts
    assert all(abs(p.price_eur_mwh - 150.0) < 1.0 for p in pts)
