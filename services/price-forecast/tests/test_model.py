from __future__ import annotations

import importlib


def test_price_rises_with_residual_load():
    m = importlib.import_module("model")
    # High irradiance + wind → low residual load → low price.
    ts = 1_700_000_000
    sunny = m.price_curve([(ts, 900.0)], [(ts, 11.0)], [(ts, 20.0)])
    dark = m.price_curve([(ts, 0.0)], [(ts, 0.0)], [(ts, -5.0)])
    assert sunny and dark
    assert sunny[0].price_eur_mwh < dark[0].price_eur_mwh
    assert sunny[0].renewable_kw > dark[0].renewable_kw


def test_price_is_bounded():
    m = importlib.import_module("model")
    ts = 1_700_000_000
    extreme = m.price_curve([(ts, 0.0)], [(ts, 0.0)], [(ts, -30.0)])
    assert extreme[0].price_eur_mwh <= m.PRICE_CAP
    assert extreme[0].price_eur_mwh >= m.PRICE_FLOOR


def test_alignment_intersects_timestamps():
    m = importlib.import_module("model")
    gti = [(100, 500.0), (200, 600.0)]
    wind = [(200, 5.0), (300, 6.0)]
    temp = [(200, 18.0)]
    pts = m.price_curve(gti, wind, temp)
    assert [p.ts for p in pts] == [200]
