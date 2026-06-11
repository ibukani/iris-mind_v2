"""Architecture guards for default SpaceBinding-free runtime wiring."""

from __future__ import annotations

from pathlib import Path

_STATE_WIRING = Path("iris/runtime/wiring/state.py")
_RUNTIME_WIRING = Path("iris/runtime/wiring")


def test_state_wiring_does_not_import_space_binding_stores() -> None:
    """Runtime state wiring must not import SpaceBinding persistence contracts."""
    source = _STATE_WIRING.read_text(encoding="utf-8")

    forbidden = (
        "SQLiteSpaceBindingStore",
        "InMemorySpaceBindingStore",
        "SpaceBindingStore",
    )

    for symbol in forbidden:
        assert symbol not in source, f"{_STATE_WIRING} must not import {symbol}"


def test_runtime_wiring_does_not_instantiate_space_binding_stores() -> None:
    """Default runtime wiring must not instantiate SpaceBinding stores."""
    forbidden = (
        "SQLiteSpaceBindingStore(",
        "InMemorySpaceBindingStore(",
    )

    for path in _RUNTIME_WIRING.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for symbol in forbidden:
            assert symbol not in source, f"{path} must not instantiate {symbol}"
