from __future__ import annotations

import importlib


def test_imports() -> None:
    mod = importlib.import_module("settlement")
    assert hasattr(mod, "app")
    assert hasattr(mod, "_settle_on_chain")


def test_dry_run_hash_deterministic() -> None:
    """In dry-run mode, the anchor returns a deterministic 0xdry-prefixed hash
    regardless of dict ordering (json.dumps uses sort_keys=True)."""
    mod = importlib.import_module("settlement")
    h1 = mod._settle_on_chain({"x": 1, "y": 2})
    h2 = mod._settle_on_chain({"y": 2, "x": 1})
    assert h1 == h2
    assert h1.startswith("0xdry")
