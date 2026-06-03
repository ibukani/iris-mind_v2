"""v0.1のランタイム配線ルール。

適用されるルール:
  1. runtime/wiringにコグニティブポリシーロジックやサービスロケータを含めてはならない。
  2. runtime/wiringは削除されたインフラストラクチャをインポートしてはならない。

層の依存方向はtest_target_architecture_guards.pyで実施される。
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


def test_runtime_wiring_no_cognitive_policy() -> None:  # noqa: C901
    """runtime/wiringにコグニティブポリシーロジックやビジネスロジックを含めてはならない。

    runtime/wiring/内の各ファイルはコンストラクタインジェクションを介してのみ依存関係を構成すべきである。
    """
    wiring_dir = _target_path("iris/runtime/wiring")
    if not wiring_dir.is_dir():
        pytest.skip("Target layer 'iris/runtime/wiring' does not exist yet")

    violations: list[str] = []

    for filepath in _get_python_files(wiring_dir):
        try:
            text = filepath.read_text(encoding="utf-8")
        except OSError:
            continue
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.ClassDef, ast.AsyncFunctionDef, ast.FunctionDef)
            ) and node.name in {
                "CognitiveCycle",
                "PipelineStep",
                "CognitiveStep",
            }:
                rel = filepath.relative_to(PROJECT_ROOT).as_posix()
                violations.append(
                    f"  {rel}: defines '{node.name}' — wiring should not define domain classes"
                )
            if isinstance(node, ast.FunctionDef) and node.name.startswith("wire_"):
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Attribute)
                        and child.func.attr in {"resolve", "get_service", "locate"}
                    ):
                        rel = filepath.relative_to(PROJECT_ROOT).as_posix()
                        violations.append(
                            f"  {rel}: calls '{child.func.attr}'"
                            " — service locator forbidden in wiring"
                        )

    assert not violations, "runtime/wiring violations found:\n" + "\n".join(violations)


def test_runtime_wiring_not_service_locator() -> None:
    """runtime/wiringはサービスロケータになってはならない。

    配線ファイルはresolve関数やサービスロケータをインポートすべきではない。
    """
    wiring_dir = _target_path("iris/runtime/wiring")
    if not wiring_dir.is_dir():
        pytest.skip("Target layer 'iris/runtime/wiring' does not exist yet")

    forbidden_imports = {"iris.kernel.manager", "iris.event"}
    violations: list[str] = []

    for filepath in _get_python_files(wiring_dir):
        rel = filepath.relative_to(PROJECT_ROOT).as_posix()
        for imp in _get_imports(filepath):
            violations.extend(
                f"  {rel}: imports '{imp}' — wiring should not depend on deleted infrastructure"
                for forbidden in forbidden_imports
                if imp.startswith(forbidden)
            )

    assert not violations, "runtime/wiring service locator violations:\n" + "\n".join(violations)
