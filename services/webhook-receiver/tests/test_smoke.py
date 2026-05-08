"""Import-and-shape smoke tests — no DB required."""
from __future__ import annotations

import importlib

import pytest


def test_module_imports() -> None:
    mod = importlib.import_module("webhook_receiver")
    assert hasattr(mod, "app")
    assert hasattr(mod, "TelemetryIn")
    assert hasattr(mod, "AssetIn")


def test_telemetry_validation() -> None:
    mod = importlib.import_module("webhook_receiver")
    sample = mod.TelemetryIn(did="did:ethr:volta:0xabc", power_w=200.0, confidence=0.9)
    assert sample.did == "did:ethr:volta:0xabc"
    with pytest.raises(Exception):
        mod.TelemetryIn(did="", power_w=1.0)


def test_asset_type_pattern() -> None:
    mod = importlib.import_module("webhook_receiver")
    mod.AssetIn(did="did:ethr:volta:0x1", asset_type="meter")
    with pytest.raises(Exception):
        mod.AssetIn(did="did:ethr:volta:0x1", asset_type="rocket")
