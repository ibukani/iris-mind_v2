"""Typed TOML table helpers for runtime config tests."""

from __future__ import annotations

from iris.runtime.config.parsing import TomlTable, TomlValue


def toml_table(**values: TomlValue) -> TomlTable:
    """Build a typed TOML table for tests."""
    return dict(values)
