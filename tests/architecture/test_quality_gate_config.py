"""Architecture guard for strict quality gate configuration."""

from __future__ import annotations

import json
from pathlib import Path
import tomllib

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

PROTECTED_MYPY_MODULES: frozenset[str] = frozenset(
    {
        "iris.contracts",
        "iris.contracts.*",
        "iris.core",
        "iris.core.*",
        "iris.cognitive",
        "iris.cognitive.*",
        "iris.features",
        "iris.features.*",
        "iris.presentation",
        "iris.presentation.*",
        "iris.safety",
        "iris.safety.*",
        "iris.runtime",
        "iris.runtime.*",
    }
)


def _pyproject() -> dict[str, object]:
    """Load pyproject.toml.

    Returns:
        dict[str, object]: Parsed contents of the project's pyproject.toml.
    """
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)


_EMPTY_DICT: dict[str, object] = {}


def _as_dict(value: object) -> dict[str, object]:
    """Coerce a config value into a dict.

    Args:
        value: Arbitrary config value extracted from TOML.

    Returns:
        dict[str, object]: The value when it is a mapping, otherwise an empty dict.
    """
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return _EMPTY_DICT


_EMPTY_LIST: list[object] = []


def _as_list(value: object) -> list[object]:
    """Coerce a config value into a list.

    Args:
        value: Arbitrary config value extracted from TOML.

    Returns:
        list[object]: The value when it is a list, otherwise an empty list.
    """
    if isinstance(value, list):
        return list(value)
    return _EMPTY_LIST


def _tool_config(name: str) -> dict[str, object]:
    """Return a tool config from pyproject.toml.

    Args:
        name: Tool section name to look up.

    Returns:
        dict[str, object]: Mapping for the requested tool section, empty if absent.
    """
    project = _pyproject()
    tool = _as_dict(project.get("tool", {}))
    return _as_dict(tool.get(name, _EMPTY_DICT))


def _tool_get(name: str, key: str) -> dict[str, object]:
    """Return a nested dict from a tool section.

    Args:
        name: Tool section name to look up.
        key: Nested key inside the tool section.

    Returns:
        dict[str, object]: Nested mapping, empty if absent.
    """
    return _as_dict(_tool_config(name).get(key, {}))


def test_ruff_all_rules_remain_selected() -> None:
    """Ruff must remain an ALL-rule strict gate."""
    ruff = _tool_config("ruff")
    lint = _as_dict(ruff.get("lint", {}))
    assert lint.get("select") == ["ALL"]


def test_mypy_strict_and_protected_any_policy_remain_enabled() -> None:
    """Mypy strict mode and protected-layer Any restrictions must not be weakened."""
    mypy = _tool_config("mypy")
    assert mypy.get("strict") is True
    assert mypy.get("disallow_any_generics") is True
    assert mypy.get("disallow_untyped_defs") is True
    assert mypy.get("warn_unused_ignores") is True

    overrides = _as_list(mypy.get("overrides", []))
    protected_override: dict[str, object] | None = None
    for override in overrides:
        override_dict = _as_dict(override)
        modules = _as_list(override_dict.get("module", []))
        module_names = frozenset(modules)
        if PROTECTED_MYPY_MODULES.issubset(module_names):
            protected_override = override_dict
            break
    assert protected_override is not None, "missing protected mypy override"
    assert protected_override.get("disallow_any_expr") is True
    assert protected_override.get("disallow_any_decorated") is True
    assert protected_override.get("disallow_any_explicit") is True


def test_pyright_strict_mode_remains_enabled() -> None:
    """Pyright must remain strict for production code."""
    config = _as_dict(json.loads((PROJECT_ROOT / "pyrightconfig.json").read_text(encoding="utf-8")))
    assert config.get("typeCheckingMode") == "strict"
    assert config.get("reportMissingImports") == "error"
    assert config.get("reportUnknownMemberType") == "error"
    assert config.get("reportUnknownVariableType") == "error"
    assert config.get("reportImportCycles") == "error"


def test_pytest_strictness_and_coverage_threshold_remain_enabled() -> None:
    """Pytest strict behavior and coverage floor must remain active."""
    pytest_config = _tool_get("pytest", "ini_options")
    addopts = pytest_config.get("addopts", "")
    assert isinstance(addopts, str)
    assert "--strict-config" in addopts
    assert "--strict-markers" in addopts
    assert pytest_config.get("xfail_strict") is True
    assert pytest_config.get("filterwarnings") == ["error"]

    coverage = _tool_get("coverage", "report")
    fail_under = coverage.get("fail_under")
    assert isinstance(fail_under, int)
    assert fail_under >= 90
