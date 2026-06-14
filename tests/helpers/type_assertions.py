"""Runtime type assertions for tests that need concrete generated types."""

from __future__ import annotations


def require_str(value: object) -> str:
    """Return value as str after a runtime assertion."""
    assert isinstance(value, str)
    return value
