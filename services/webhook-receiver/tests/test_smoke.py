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


class _FakeReq:
    def __init__(self, token=None):
        self.headers = {} if token is None else {"x-ingest-token": token}


def test_require_token_rejects_missing_and_wrong() -> None:
    from fastapi import HTTPException
    mod = importlib.import_module("webhook_receiver")
    with pytest.raises(HTTPException) as e1:
        mod.require_token(_FakeReq())               # no header
    assert e1.value.status_code == 401
    with pytest.raises(HTTPException):
        mod.require_token(_FakeReq("wrong-token"))  # wrong value
    # correct token (module default in dev) must not raise
    mod.require_token(_FakeReq(mod.INGEST_TOKEN))


def test_sensitive_write_endpoints_require_token() -> None:
    """assets, shares, and incentive POSTs must carry the require_token dep."""
    mod = importlib.import_module("webhook_receiver")

    def has_token_dep(dependant) -> bool:
        if getattr(dependant, "call", None) is mod.require_token:
            return True
        return any(has_token_dep(d) for d in getattr(dependant, "dependencies", []))

    protected = {"/api/v1/assets", "/api/shares", "/api/internal/incentive",
                 "/api/v1/telemetry/ingest", "/api/v1/mainflux/webhook"}
    seen = set()
    for route in mod.app.routes:
        if getattr(route, "path", None) in protected and "POST" in getattr(route, "methods", set()):
            assert has_token_dep(route.dependant), f"{route.path} missing require_token"
            seen.add(route.path)
    assert seen == protected
