"""Runtime wiring rules for v0.1.

Rules enforced:
  1. runtime/wiring must not contain cognitive policy logic or service locator.
  2. runtime/wiring must not import deleted infrastructure.

Layer dependency direction is enforced by test_target_architecture_guards.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ── Helpers ─────────────────────────────────────────────────────


def _target_path(rel_dir: str) -> Path:
    return PROJECT_ROOT / rel_dir


def _get_python_files(base: Path) -> list[Path]:
    return sorted(base.rglob("*.py"))


def _get_imports(filepath: Path) -> list[str]:
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


# ── 1. Runtime wiring rules ────────────────────────────────────


def test_runtime_wiring_no_cognitive_policy() -> None:
    """runtime/wiring must not contain cognitive policy logic or business logic.

    Each file in runtime/wiring/ should only compose dependencies
    via constructor injection.
    """
    wiring_dir = _target_path("iris/runtime/wiring")
    if not wiring_dir.is_dir():
        pytest.skip("Target layer 'iris/runtime/wiring' does not exist yet")

    violations: list[str] = []

    for filepath in _get_python_files(wiring_dir):
        try:
            text = filepath.read_text(encoding="utf-8")
        except Exception:  # noqa: S112
            continue
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef, ast.FunctionDef)) and node.name in {
                "CognitiveCycle",
                "PipelineStep",
                "CognitiveStep",
            }:
                rel = filepath.relative_to(PROJECT_ROOT).as_posix()
                violations.append(f"  {rel}: defines '{node.name}' — wiring should not define domain classes")
            if isinstance(node, ast.FunctionDef) and node.name.startswith("wire_"):
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Attribute)
                        and child.func.attr in {"resolve", "get_service", "locate"}
                    ):
                        rel = filepath.relative_to(PROJECT_ROOT).as_posix()
                        violations.append(f"  {rel}: calls '{child.func.attr}' — service locator forbidden in wiring")

    assert not violations, "runtime/wiring violations found:\n" + "\n".join(violations)


def test_runtime_wiring_not_service_locator() -> None:
    """runtime/wiring must not become a service locator.

    Wiring files should not import resolve functions or service locators.
    """
    wiring_dir = _target_path("iris/runtime/wiring")
    if not wiring_dir.is_dir():
        pytest.skip("Target layer 'iris/runtime/wiring' does not exist yet")

    forbidden_imports = {"iris.kernel.manager", "iris.event"}
    violations: list[str] = []

    for filepath in _get_python_files(wiring_dir):
        rel = filepath.relative_to(PROJECT_ROOT).as_posix()
        for imp in _get_imports(filepath):
            for forbidden in forbidden_imports:
                if imp.startswith(forbidden):
                    violations.append(f"  {rel}: imports '{imp}' — wiring should not depend on deleted infrastructure")

    assert not violations, "runtime/wiring service locator violations:\n" + "\n".join(violations)
