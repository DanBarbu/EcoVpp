from __future__ import annotations

import importlib


def test_zone_registry_integrity():
    z = importlib.import_module("zones")
    codes = z.all_codes()
    assert "RO" in codes
    assert len(codes) >= 27  # EU-27 principal zones (+ a few split zones)
    seen_eic = set()
    for code in codes:
        zone = z.get(code)
        assert zone.eic and zone.eic not in seen_eic, f"dup/empty EIC for {code}"
        seen_eic.add(zone.eic)
        assert -32 <= zone.lon <= 35 and 34 <= zone.lat <= 71, f"{code} centroid off-map"


def test_zone_lookup_case_insensitive_and_errors():
    z = importlib.import_module("zones")
    assert z.get("ro").code == "RO"
    try:
        z.get("XX")
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_a44_parser():
    m = importlib.import_module("markets")
    xml = """<?xml version="1.0"?>
    <Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
      <TimeSeries>
        <Period>
          <timeInterval><start>2026-01-01T00:00Z</start><end>2026-01-01T02:00Z</end></timeInterval>
          <resolution>PT60M</resolution>
          <Point><position>1</position><price.amount>80.5</price.amount></Point>
          <Point><position>2</position><price.amount>95.0</price.amount></Point>
        </Period>
      </TimeSeries>
    </Publication_MarketDocument>"""
    series = m.parse_a44(xml)
    assert len(series) == 2
    assert series[0][1] == 80.5 and series[1][1] == 95.0
    assert series[1][0] - series[0][0] == 3600  # one hour apart


def test_calibration_path_for_zone():
    cal = importlib.import_module("calibration")
    assert cal.path_for("DE_LU").endswith("calibration.DE_LU.json")
    assert cal.path_for(None) == cal.CALIBRATION_FILE
