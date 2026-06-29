"""Tests for runtime config parsing helpers."""

from __future__ import annotations

import io
import math

import pytest

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import (
    TomlTable,
    env_float,
    env_optional_float,
    env_optional_int,
    load_toml,
    parse_float,
    parse_int,
    parse_optional_float,
    parse_optional_int,
    parse_optional_string,
    parse_string,
    table_or_empty,
)
from tests.helpers.exact_eq import assert_exact_eq


def test_load_toml_parses_document() -> None:
    """load_toml reads a TOML document from a binary stream."""
    file = io.BytesIO(b"a = 1\nb = 'hello'\n")
    result = load_toml(file)
    assert result == {"a": 1, "b": "hello"}


def test_table_or_empty_returns_nested_table() -> None:
    """table_or_empty returns the nested table when present."""
    table: TomlTable = {"section": {"key": "value"}}
    assert table_or_empty(table, "section") == {"key": "value"}


def test_table_or_empty_returns_empty_when_missing() -> None:
    """table_or_empty returns an empty dict when the key is absent."""
    assert table_or_empty({}, "missing") == {}


def test_table_or_empty_raises_when_value_is_not_table() -> None:
    """table_or_empty raises ConfigError when the value is not a dict."""
    with pytest.raises(ConfigError, match="must be a table"):
        table_or_empty({"section": "not-a-table"}, "section")


def test_table_or_empty_raises_with_explicit_path() -> None:
    """table_or_empty は指定時に完全な設定 path で型エラーを返す。"""
    with pytest.raises(ConfigError, match=r"root\.section must be a table"):
        table_or_empty({"section": "invalid"}, "section", path="root.section")


def test_parse_string_returns_string() -> None:
    """parse_string returns the string value."""
    assert parse_string("hello", "path") == "hello"


def test_parse_string_raises_on_non_string() -> None:
    """parse_string raises ConfigError for non-string values."""
    with pytest.raises(ConfigError, match="must be a string"):
        parse_string(123, "path")


def test_parse_optional_string_returns_none() -> None:
    """parse_optional_string returns None for None input."""
    assert parse_optional_string(None, "path") is None


def test_parse_optional_string_returns_string() -> None:
    """parse_optional_string returns the string value."""
    assert parse_optional_string("hello", "path") == "hello"


def test_parse_optional_string_raises_on_invalid_type() -> None:
    """parse_optional_string raises ConfigError for invalid types."""
    with pytest.raises(ConfigError, match="must be a string or null"):
        parse_optional_string(123, "path")


def test_parse_int_returns_int() -> None:
    """parse_int returns the integer value."""
    assert parse_int(42, "path") == 42


def test_parse_int_rejects_bool() -> None:
    """parse_int raises ConfigError for bool values (special case)."""
    with pytest.raises(ConfigError, match="must be an integer"):
        parse_int(value=True, path="path")


def test_parse_int_raises_on_non_int() -> None:
    """parse_int raises ConfigError for non-integer values."""
    with pytest.raises(ConfigError, match="must be an integer"):
        parse_int("42", "path")


def test_parse_optional_int_returns_none() -> None:
    """parse_optional_int returns None for None input."""
    assert parse_optional_int(None, "path") is None


def test_parse_optional_int_returns_int() -> None:
    """parse_optional_int delegates to parse_int for non-None values."""
    assert parse_optional_int(42, "path") == 42


def test_parse_float_returns_float() -> None:
    """parse_float returns the float value."""
    assert parse_float(math.pi, "path") == math.pi


def test_parse_float_converts_int() -> None:
    """parse_float converts int to float."""
    assert_exact_eq(parse_float(42, "path"), 42.0)


def test_parse_float_rejects_bool() -> None:
    """parse_float raises ConfigError for bool values."""
    with pytest.raises(ConfigError, match="must be a float"):
        parse_float(value=True, path="path")


def test_parse_float_raises_on_non_number() -> None:
    """parse_float raises ConfigError for non-numeric values."""
    with pytest.raises(ConfigError, match="must be a float"):
        parse_float("3.14", "path")


def test_parse_optional_float_returns_none() -> None:
    """parse_optional_float returns None for None input."""
    assert parse_optional_float(None, "path") is None


def test_parse_optional_float_returns_float() -> None:
    """parse_optional_float delegates to parse_float for non-None values."""
    assert parse_optional_float(math.pi, "path") == math.pi


def test_env_float_returns_default_when_missing() -> None:
    """env_float returns the default when the variable is absent."""
    assert_exact_eq(env_float({}, "MISSING", default=1.5), 1.5)


def test_env_float_parses_valid_value() -> None:
    """env_float parses a valid float string."""
    assert_exact_eq(env_float({"VAR": "2.5"}, "VAR", default=1.5), 2.5)


def test_env_float_raises_on_invalid_value() -> None:
    """env_float raises ConfigError for non-float strings."""
    with pytest.raises(ConfigError, match="must be a float"):
        env_float({"VAR": "not-a-float"}, "VAR", 1.5)


def test_env_optional_float_returns_default_when_missing() -> None:
    """env_optional_float returns the default when the variable is absent."""
    assert_exact_eq(env_optional_float({}, "MISSING", default=1.5), 1.5)


def test_env_optional_float_returns_none_when_default_none() -> None:
    """env_optional_float returns None when the variable is absent and default is None."""
    assert env_optional_float({}, "MISSING", None) is None


def test_env_optional_float_parses_valid_value() -> None:
    """env_optional_float parses a valid float string."""
    assert_exact_eq(env_optional_float({"VAR": "2.5"}, "VAR", default=1.5), 2.5)


def test_env_optional_float_raises_on_invalid_value() -> None:
    """env_optional_float raises ConfigError for non-float strings."""
    with pytest.raises(ConfigError, match="must be a float"):
        env_optional_float({"VAR": "bad"}, "VAR", 1.5)


def test_env_optional_int_returns_default_when_missing() -> None:
    """env_optional_int returns the default when the variable is absent."""
    assert env_optional_int({}, "MISSING", 42) == 42


def test_env_optional_int_returns_none_when_default_none() -> None:
    """env_optional_int returns None when the variable is absent and default is None."""
    assert env_optional_int({}, "MISSING", None) is None


def test_env_optional_int_parses_valid_value() -> None:
    """env_optional_int parses a valid integer string."""
    assert env_optional_int({"VAR": "100"}, "VAR", 42) == 100


def test_env_optional_int_raises_on_invalid_value() -> None:
    """env_optional_int raises ConfigError for non-integer strings."""
    with pytest.raises(ConfigError, match="must be an integer"):
        env_optional_int({"VAR": "not-an-int"}, "VAR", 42)
