from __future__ import annotations

import importlib


def test_to_kw_conversion() -> None:
    mod = importlib.import_module("forecast")
    # Default panel: 5 kWp at 0.85 efficiency
    out = mod.to_kw([0.0, 500.0, 1000.0])
    assert out[0] == 0.0
    assert abs(out[1] - 5.0 * 0.5 * 0.85) < 1e-3
    assert abs(out[2] - 5.0 * 1.0 * 0.85) < 1e-3
