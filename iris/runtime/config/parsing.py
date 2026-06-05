"""Generic TOML and environment value parsing helpers for runtime config."""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

from iris.runtime.config.errors import ConfigError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from typing import BinaryIO

type TomlScalar = str | int | float | bool | None
type TomlValue = TomlScalar | TomlArray | TomlTable
type TomlArray = list[TomlValue]
type TomlTable = dict[str, TomlValue]

_load_toml: Callable[[BinaryIO], TomlTable] = tomllib.load


def load_toml(file: BinaryIO) -> TomlTable:
    """Load a TOML document from an open binary file.

    Args:
        file: Open binary file handle positioned at the TOML document.

    Returns:
        Parsed top-level TOML table.
    """
    return _load_toml(file)


def table_or_empty(table: TomlTable, key: str) -> TomlTable:
    """Return a nested table or an empty table when absent.

    Args:
        table: Parent TOML table.
        key: Nested table key to read.

    Returns:
        Nested TOML table, or an empty table when the key is missing.

    Raises:
        ConfigError: If the value exists but is not a table.
    """
    value = table.get(key)
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    message = f"Runtime config section '{key}' must be a table"
    raise ConfigError(message)


def parse_string(value: TomlValue, path: str) -> str:
    """Parse a required string TOML value.

    Args:
        value: TOML value to validate.
        path: Config path used in error messages.

    Returns:
        Validated string value.

    Raises:
        ConfigError: If the value is not a string.
    """
    if isinstance(value, str):
        return value
    message = f"Runtime config value '{path}' must be a string"
    raise ConfigError(message)


def parse_optional_string(value: TomlValue, path: str) -> str | None:
    """Parse an optional string TOML value.

    Args:
        value: TOML value to validate.
        path: Config path used in error messages.

    Returns:
        Validated string value or ``None``.

    Raises:
        ConfigError: If the value is not a string or null.
    """
    if value is None or isinstance(value, str):
        return value
    message = f"Runtime config value '{path}' must be a string or null"
    raise ConfigError(message)


def parse_int(value: TomlValue, path: str) -> int:
    """Parse a required integer TOML value.

    Args:
        value: TOML value to validate.
        path: Config path used in error messages.

    Returns:
        Validated integer value.

    Raises:
        ConfigError: If the value is not an integer.
    """
    if isinstance(value, bool):
        message = f"Runtime config value '{path}' must be an integer"
        raise ConfigError(message)
    if isinstance(value, int):
        return value
    message = f"Runtime config value '{path}' must be an integer"
    raise ConfigError(message)


def parse_optional_int(value: TomlValue, path: str) -> int | None:
    """Parse an optional integer TOML value.

    Args:
        value: TOML value to validate.
        path: Config path used in error messages.

    Returns:
        Validated integer value or ``None``.
    """
    if value is None:
        return None
    return parse_int(value, path)


def parse_float(value: TomlValue, path: str) -> float:
    """Parse a required float TOML value.

    Args:
        value: TOML value to validate.
        path: Config path used in error messages.

    Returns:
        Validated float value.

    Raises:
        ConfigError: If the value is not numeric.
    """
    if isinstance(value, bool):
        message = f"Runtime config value '{path}' must be a float"
        raise ConfigError(message)
    if isinstance(value, (int, float)):
        return float(value)
    message = f"Runtime config value '{path}' must be a float"
    raise ConfigError(message)


def parse_optional_float(value: TomlValue, path: str) -> float | None:
    """Parse an optional float TOML value.

    Args:
        value: TOML value to validate.
        path: Config path used in error messages.

    Returns:
        Validated float value or ``None``.
    """
    if value is None:
        return None
    return parse_float(value, path)


def env_float(env: Mapping[str, str], key: str, default: float) -> float:
    """Read a required float environment variable.

    Args:
        env: Environment variable mapping.
        key: Variable name.
        default: Default value to return when the variable is absent.

    Returns:
        Parsed float value or the default.

    Raises:
        ConfigError: If the value cannot be parsed as float.
    """
    value = env.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        message = f"Environment variable {key} must be a float"
        raise ConfigError(message) from exc


def env_optional_float(env: Mapping[str, str], key: str, default: float | None) -> float | None:
    """Read an optional float environment variable.

    Args:
        env: Environment variable mapping.
        key: Variable name.
        default: Default value to return when the variable is absent.

    Returns:
        Parsed float value, ``None``, or the default.

    Raises:
        ConfigError: If the value cannot be parsed as float.
    """
    value = env.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        message = f"Environment variable {key} must be a float"
        raise ConfigError(message) from exc


def env_optional_int(env: Mapping[str, str], key: str, default: int | None) -> int | None:
    """Read an optional integer environment variable.

    Args:
        env: Environment variable mapping.
        key: Variable name.
        default: Default value to return when the variable is absent.

    Returns:
        Parsed integer value, ``None``, or the default.

    Raises:
        ConfigError: If the value cannot be parsed as integer.
    """
    value = env.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        message = f"Environment variable {key} must be an integer"
        raise ConfigError(message) from exc
