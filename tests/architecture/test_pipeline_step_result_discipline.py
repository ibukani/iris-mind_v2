"""PipelineStep.run が typed result 以外を返さないことを検査する。"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from tests.architecture.helpers.ast_utils import name_of, parse_python_file
from tests.architecture.helpers.project_paths import IRIS_ROOT

if TYPE_CHECKING:
    from pathlib import Path


def _cognitive_python_files() -> tuple[Path, ...]:
    return tuple(sorted((IRIS_ROOT / "cognitive").rglob("*.py")))


def _is_pipeline_step_class(node: ast.ClassDef) -> bool:
    return any(name_of(base) == "PipelineStep" for base in node.bases)


def _run_methods(path: Path) -> list[ast.AsyncFunctionDef]:
    methods: list[ast.AsyncFunctionDef] = []
    for node in ast.walk(parse_python_file(path)):
        if isinstance(node, ast.ClassDef) and _is_pipeline_step_class(node):
            methods.extend(
                item
                for item in node.body
                if isinstance(item, ast.AsyncFunctionDef) and item.name == "run"
            )
    return methods


def _is_forbidden_return(node: ast.Return) -> bool:
    value = node.value
    if value is None:
        return True
    if isinstance(value, ast.Constant) and value.value is None:
        return True
    if isinstance(value, ast.Name) and value.id == "frame":
        return True
    return isinstance(value, (ast.Dict, ast.List, ast.Tuple))


def test_pipeline_steps_return_typed_results() -> None:
    """PipelineStep.run は WorkspaceFrame や raw container を返さない。"""
    violations: list[str] = []
    for path in _cognitive_python_files():
        for method in _run_methods(path):
            violations.extend(
                f"{path}:{node.lineno}: forbidden PipelineStep return"
                for node in ast.walk(method)
                if isinstance(node, ast.Return) and _is_forbidden_return(node)
            )
    assert not violations, "\n".join(violations)
