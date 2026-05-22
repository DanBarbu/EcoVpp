from __future__ import annotations

import importlib


def test_parse_energycharts_payload():
    ec = importlib.import_module("energycharts")
    payload = {
        "unix_seconds": [1700000000, 1700003600, 1700007200],
        "price": [80.5, 95.0, 60.25],
        "unit": "EUR/MWh",
    }
    series = ec.parse(payload)
    assert len(series) == 3
    assert series[0] == (1700000000, 80.5)
    assert series[-1][1] == 60.25
    # ascending by time
    assert [t for t, _ in series] == sorted(t for t, _ in series)


def test_parse_skips_nulls_and_handles_empty():
    ec = importlib.import_module("energycharts")
    assert ec.parse({}) == []
    payload = {"unix_seconds": [1, 2, 3], "price": [10.0, None, 30.0]}
    series = ec.parse(payload)
    assert len(series) == 2
    assert (2, None) not in series


def test_every_zone_has_a_source():
    z = importlib.import_module("zones")
    # Every zone must be reachable by at least one source (Energy-Charts ec code
    # or an ENTSO-E EIC). Only isolated islands (CY, MT) may lack the ec code.
    for code in z.all_codes():
        zone = z.get(code)
        assert zone.eic, f"{code} missing EIC"
        if not zone.ec:
            assert code in {"CY", "MT"}, f"{code} unexpectedly lacks Energy-Charts code"
