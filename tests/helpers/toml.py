"""Typed TOML table helpers for runtime config tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.runtime.config.parsing import TomlTable, TomlValue


def toml_table(**values: TomlValue) -> TomlTable:
    """Build a typed TOML table for tests.

    Returns:
        TomlTable: テスト用のtyped TOML table。
    """
    return dict(values)
