"""Import-and-shape + physics tests — no DB required."""
from __future__ import annotations

import importlib

import pytest


def test_module_imports() -> None:
    mod = importlib.import_module("hydrobattery_atlas")
    assert hasattr(mod, "app")
    assert hasattr(mod, "HydrobatteryIn")
    assert hasattr(mod, "storage_capacity_kwh")
    assert hasattr(mod, "dispatch_plan")


def test_storage_capacity_physics() -> None:
    mod = importlib.import_module("hydrobattery_atlas")
    # E = rho*g*V*h*eta / 3.6e6 ; with V=1e6, h=300, eta=0.8
    expected = 1000.0 * 9.81 * 1_000_000.0 * 300.0 * 0.8 / 3_600_000.0
    got = mod.storage_capacity_kwh(head_m=300.0, usable_volume_m3=1_000_000.0, round_trip_efficiency=0.8)
    assert got == pytest.approx(expected)
    assert got == pytest.approx(654_000.0, rel=1e-6)


def test_storage_capacity_zero_on_nonpositive() -> None:
    mod = importlib.import_module("hydrobattery_atlas")
    assert mod.storage_capacity_kwh(head_m=0.0, usable_volume_m3=1000.0, round_trip_efficiency=0.8) == 0.0
    assert mod.storage_capacity_kwh(head_m=100.0, usable_volume_m3=0.0, round_trip_efficiency=0.8) == 0.0


def test_resolved_capacity_prefers_override() -> None:
    mod = importlib.import_module("hydrobattery_atlas")
    site = mod.HydrobatteryIn(
        name="Site A", latitude=45.0, longitude=25.0,
        head_m=300.0, usable_volume_m3=1_000_000.0, rated_power_kw=100_000.0,
        storage_capacity_kwh=42.0,
    )
    assert site.resolved_capacity_kwh() == 42.0


def test_resolved_capacity_derives_when_absent() -> None:
    mod = importlib.import_module("hydrobattery_atlas")
    site = mod.HydrobatteryIn(
        name="Site B", latitude=45.0, longitude=25.0,
        head_m=300.0, usable_volume_m3=1_000_000.0, rated_power_kw=100_000.0,
        round_trip_efficiency=0.8,
    )
    assert site.resolved_capacity_kwh() == pytest.approx(654_000.0, rel=1e-6)


def test_dispatch_feasible() -> None:
    mod = importlib.import_module("hydrobattery_atlas")
    plan = mod.dispatch_plan(
        rated_power_kw=100_000.0, storage_kwh=654_000.0, state_of_charge=0.5,
        power_kw=50_000.0, hours=2.0,
    )
    assert plan["feasible"] is True
    assert plan["limiting_factor"] is None
    assert plan["available_kwh"] == pytest.approx(327_000.0)


def test_dispatch_power_limited() -> None:
    mod = importlib.import_module("hydrobattery_atlas")
    plan = mod.dispatch_plan(
        rated_power_kw=10_000.0, storage_kwh=654_000.0, state_of_charge=0.5,
        power_kw=50_000.0, hours=1.0,
    )
    assert plan["feasible"] is False
    assert plan["limiting_factor"] == "power"
    assert plan["deliverable_power_kw"] == 10_000.0


def test_dispatch_energy_limited() -> None:
    mod = importlib.import_module("hydrobattery_atlas")
    plan = mod.dispatch_plan(
        rated_power_kw=100_000.0, storage_kwh=100.0, state_of_charge=0.1,
        power_kw=50.0, hours=10.0,
    )
    assert plan["feasible"] is False
    assert plan["limiting_factor"] == "energy"


def test_status_validation() -> None:
    mod = importlib.import_module("hydrobattery_atlas")
    mod.HydrobatteryIn(
        name="ok", latitude=0.0, longitude=0.0, head_m=1.0,
        usable_volume_m3=1.0, rated_power_kw=1.0, status="planned",
    )
    with pytest.raises(Exception):
        mod.HydrobatteryIn(
            name="bad", latitude=0.0, longitude=0.0, head_m=1.0,
            usable_volume_m3=1.0, rated_power_kw=1.0, status="rocket",
        )


def test_coordinate_bounds_enforced() -> None:
    mod = importlib.import_module("hydrobattery_atlas")
    with pytest.raises(Exception):
        mod.HydrobatteryIn(
            name="x", latitude=120.0, longitude=0.0, head_m=1.0,
            usable_volume_m3=1.0, rated_power_kw=1.0,
        )


class _FakeReq:
    def __init__(self, token=None):
        self.headers = {} if token is None else {"x-ingest-token": token}


def test_require_token_rejects_missing_and_wrong() -> None:
    from fastapi import HTTPException
    mod = importlib.import_module("hydrobattery_atlas")
    with pytest.raises(HTTPException) as e1:
        mod.require_token(_FakeReq())
    assert e1.value.status_code == 401
    with pytest.raises(HTTPException):
        mod.require_token(_FakeReq("wrong-token"))
    mod.require_token(_FakeReq(mod.INGEST_TOKEN))


def test_write_endpoints_require_token() -> None:
    """Create, SoC update, and delete must carry the require_token dep."""
    mod = importlib.import_module("hydrobattery_atlas")

    def has_token_dep(dependant) -> bool:
        if getattr(dependant, "call", None) is mod.require_token:
            return True
        return any(has_token_dep(d) for d in getattr(dependant, "dependencies", []))

    protected = {
        ("/api/v1/hydrobatteries", "POST"),
        ("/api/v1/hydrobatteries/{site_id}/soc", "PATCH"),
        ("/api/v1/hydrobatteries/{site_id}", "DELETE"),
    }
    seen = set()
    for route in mod.app.routes:
        path = getattr(route, "path", None)
        for method in getattr(route, "methods", set()) or set():
            if (path, method) in protected:
                assert has_token_dep(route.dependant), f"{method} {path} missing require_token"
                seen.add((path, method))
    assert seen == protected
