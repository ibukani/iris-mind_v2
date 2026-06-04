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
    """Load pyproject.toml."""
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)


def _tool_config(name: str) -> dict[str, object]:
    """Return a tool config from pyproject.toml."""
    project = _pyproject()
    tool = project.get("tool", {})
    assert isinstance(tool, dict)
    config = tool.get(name, {})
    assert isinstance(config, dict)
    return config


def test_ruff_all_rules_remain_selected() -> None:
    """Ruff must remain an ALL-rule strict gate."""
    ruff = _tool_config("ruff")
    lint = ruff.get("lint", {})
    assert isinstance(lint, dict)
    assert lint.get("select") == ["ALL"]


def test_mypy_strict_and_protected_any_policy_remain_enabled() -> None:
    """mypy strict mode and protected-layer Any restrictions must not be weakened."""
    mypy = _tool_config("mypy")
    assert mypy.get("strict") is True
    assert mypy.get("disallow_any_generics") is True
    assert mypy.get("disallow_untyped_defs") is True
    assert mypy.get("warn_unused_ignores") is True

    overrides = mypy.get("overrides", [])
    assert isinstance(overrides, list)
    protected_override = None
    for override in overrides:
        assert isinstance(override, dict)
        modules = override.get("module", [])
        if isinstance(modules, list) and PROTECTED_MYPY_MODULES.issubset(set(modules)):
            protected_override = override
            break
    assert protected_override is not None, "missing protected mypy override"
    assert protected_override.get("disallow_any_expr") is True
    assert protected_override.get("disallow_any_decorated") is True
    assert protected_override.get("disallow_any_explicit") is True


def test_pyright_strict_mode_remains_enabled() -> None:
    """pyright must remain strict for production code."""
    config = json.loads((PROJECT_ROOT / "pyrightconfig.json").read_text(encoding="utf-8"))
    assert config.get("typeCheckingMode") == "strict"
    assert config.get("reportMissingImports") == "error"
    assert config.get("reportUnknownMemberType") == "error"
    assert config.get("reportUnknownVariableType") == "error"
    assert config.get("reportImportCycles") == "error"


def test_pytest_strictness_and_coverage_threshold_remain_enabled() -> None:
    """pytest strict behavior and coverage floor must remain active."""
    pytest_config = _tool_config("pytest").get("ini_options", {})
    assert isinstance(pytest_config, dict)
    addopts = pytest_config.get("addopts", "")
    assert isinstance(addopts, str)
    assert "--strict-config" in addopts
    assert "--strict-markers" in addopts
    assert pytest_config.get("xfail_strict") is True
    assert pytest_config.get("filterwarnings") == ["error"]

    coverage = _tool_config("coverage").get("report", {})
    assert isinstance(coverage, dict)
    fail_under = coverage.get("fail_under")
    assert isinstance(fail_under, int)
    assert fail_under >= 90
