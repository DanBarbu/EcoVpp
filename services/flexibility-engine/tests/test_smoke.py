from __future__ import annotations

import importlib
from datetime import datetime, timezone


def test_imports() -> None:
    mod = importlib.import_module("flexibility_engine")
    assert hasattr(mod, "GridSignal")
    assert hasattr(mod, "build_command")


def test_curtailment_curve() -> None:
    mod = importlib.import_module("flexibility_engine")
    low = mod.GridSignal(price_eur_mwh=20.0, timestamp=datetime.now(tz=timezone.utc))
    mid = mod.GridSignal(price_eur_mwh=120.0, timestamp=datetime.now(tz=timezone.utc))
    high = mod.GridSignal(price_eur_mwh=300.0, timestamp=datetime.now(tz=timezone.utc))
    assert low.curtailment == 0.0
    assert 0.3 < mid.curtailment < 0.7
    assert high.curtailment == 1.0


def test_command_shape() -> None:
    mod = importlib.import_module("flexibility_engine")
    sig = mod.GridSignal(price_eur_mwh=120.0, timestamp=datetime.now(tz=timezone.utc))
    cmd = mod.build_command(sig)
    assert cmd["command"] == "SET_LOAD_LIMIT"
    assert 0.0 <= cmd["limit_pct"] <= 100.0
    assert "issued_at" in cmd
