"""EU day-ahead bidding-zone registry.

Each zone carries its ENTSO-E EIC code (used for the A44 day-ahead price query)
and a centroid lat/lon (used to pull the weather that drives the model). For
countries with multiple bidding zones (IT, SE, DK, NO outside EU) a single
representative zone is listed; append the others as needed — the calibration
machinery is per-zone and zone-agnostic.

Correlation is scale-invariant and the OLS calibration absorbs linear capacity
scaling, so per-country installed PV/wind capacities are NOT needed here: the
same merit-order model (default capacities) is correlated against each market,
and below threshold the forecast anchors to that market's real price.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Zone:
    code: str       # short key used for calibration.<code>.json
    name: str
    eic: str        # ENTSO-E bidding-zone EIC
    lat: float
    lon: float
    ec: str = ""    # Energy-Charts bidding-zone code (token-free source); "" if unavailable


# EU-27 principal day-ahead bidding zones (representative zone for multi-zone members).
# `ec` is the Energy-Charts (Fraunhofer ISE) bidding-zone code — the default,
# token-free source. `eic` is the ENTSO-E code used when a token is supplied.
EU_ZONES: dict[str, Zone] = {
    "AT": Zone("AT", "Austria", "10YAT-APG------L", 47.6, 14.1, "AT"),
    "BE": Zone("BE", "Belgium", "10YBE----------2", 50.6, 4.6, "BE"),
    "BG": Zone("BG", "Bulgaria", "10YCA-BULGARIA-R", 42.7, 25.5, "BG"),
    "HR": Zone("HR", "Croatia", "10YHR-HEP------M", 45.1, 15.5, "HR"),
    "CY": Zone("CY", "Cyprus", "10YCY-1001A0003J", 35.0, 33.0, ""),
    "CZ": Zone("CZ", "Czechia", "10YCZ-CEPS-----N", 49.8, 15.5, "CZ"),
    "DK1": Zone("DK1", "Denmark West", "10YDK-1--------W", 56.3, 9.5, "DK1"),
    "DK2": Zone("DK2", "Denmark East", "10YDK-2--------M", 55.5, 12.0, "DK2"),
    "EE": Zone("EE", "Estonia", "10Y1001A1001A39I", 58.7, 25.5, "EE"),
    "FI": Zone("FI", "Finland", "10YFI-1--------U", 62.5, 26.0, "FI"),
    "FR": Zone("FR", "France", "10YFR-RTE------C", 46.6, 2.5, "FR"),
    "DE_LU": Zone("DE_LU", "Germany-Luxembourg", "10Y1001A1001A82H", 51.1, 10.4, "DE-LU"),
    "GR": Zone("GR", "Greece", "10YGR-HTSO-----Y", 39.0, 22.0, "GR"),
    "HU": Zone("HU", "Hungary", "10YHU-MAVIR----U", 47.2, 19.5, "HU"),
    "IE": Zone("IE", "Ireland (SEM)", "10Y1001A1001A59C", 53.4, -8.0, "IE"),
    "IT_NORD": Zone("IT_NORD", "Italy North", "10Y1001A1001A73I", 45.5, 9.5, "IT-North"),
    "IT_CNOR": Zone("IT_CNOR", "Italy Centre-North", "10Y1001A1001A70O", 43.5, 11.5, "IT-Centre-North"),
    "IT_SUD": Zone("IT_SUD", "Italy South", "10Y1001A1001A788", 40.5, 16.5, "IT-South"),
    "LV": Zone("LV", "Latvia", "10YLV-1001A00074", 56.9, 24.6, "LV"),
    "LT": Zone("LT", "Lithuania", "10YLT-1001A0008Q", 55.2, 23.9, "LT"),
    "MT": Zone("MT", "Malta", "10Y1001A1001A93C", 35.9, 14.4, ""),
    "NL": Zone("NL", "Netherlands", "10YNL----------L", 52.1, 5.3, "NL"),
    "PL": Zone("PL", "Poland", "10YPL-AREA-----S", 52.1, 19.4, "PL"),
    "PT": Zone("PT", "Portugal", "10YPT-REN------W", 39.6, -8.0, "PT"),
    "RO": Zone("RO", "Romania", "10YRO-TEL------P", 45.9, 25.0, "RO"),
    "SK": Zone("SK", "Slovakia", "10YSK-SEPS-----K", 48.7, 19.5, "SK"),
    "SI": Zone("SI", "Slovenia", "10YSI-ELES-----O", 46.1, 14.8, "SI"),
    "ES": Zone("ES", "Spain", "10YES-REE------0", 40.3, -3.7, "ES"),
    "SE3": Zone("SE3", "Sweden SE3", "10Y1001A1001A46L", 59.3, 15.5, "SE3"),
    "SE4": Zone("SE4", "Sweden SE4", "10Y1001A1001A47J", 56.0, 13.5, "SE4"),
}


def get(code: str) -> Zone:
    z = EU_ZONES.get(code) or EU_ZONES.get(code.upper())
    if not z:
        raise KeyError(f"unknown zone '{code}'. Known: {', '.join(EU_ZONES)}")
    return z


def all_codes() -> list[str]:
    return list(EU_ZONES)
