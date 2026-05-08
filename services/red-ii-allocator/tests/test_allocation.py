from __future__ import annotations

import importlib


def test_pro_rata_share_when_demand_exceeds_production() -> None:
    mod = importlib.import_module("allocator")
    consumers = [("a", 4.0), ("b", 6.0)]
    allocations, surplus = mod.allocate(production_kwh=5.0, consumers=consumers)
    total = sum(a[1] for a in allocations)
    assert surplus == 0.0
    assert abs(total - 5.0) < 1e-6
    # ratios preserved
    a_share = next(v for k, v in allocations if k == "a")
    b_share = next(v for k, v in allocations if k == "b")
    assert b_share > a_share


def test_surplus_when_production_exceeds_demand() -> None:
    mod = importlib.import_module("allocator")
    allocations, surplus = mod.allocate(10.0, [("a", 2.0), ("b", 3.0)])
    assert surplus == 5.0
    assert sum(a[1] for a in allocations) == 5.0


def test_no_demand() -> None:
    mod = importlib.import_module("allocator")
    allocations, surplus = mod.allocate(7.0, [])
    assert allocations == []
    assert surplus == 7.0
