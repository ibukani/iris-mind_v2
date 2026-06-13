"""Global mutable registry / service locator 形状を禁止する。"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from tests.architecture.helpers.ast_utils import name_of, parse_python_file
from tests.architecture.helpers.project_paths import IRIS_ROOT

if TYPE_CHECKING:
    from pathlib import Path

TARGET_NAME_PARTS = (
    "registry",
    "registries",
    "service",
    "services",
    "plugin",
    "plugins",
    "locator",
)
MUTABLE_CONSTRUCTORS = {"dict", "list", "set"}


def _target_files() -> tuple[Path, ...]:
    return tuple(sorted(IRIS_ROOT.rglob("*.py")))


def _is_mutable_literal(node: ast.AST) -> bool:
    if isinstance(node, (ast.Dict, ast.List, ast.Set)):
        return True
    return isinstance(node, ast.Call) and name_of(node.func) in MUTABLE_CONSTRUCTORS


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> tuple[str, ...]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return tuple(target.id for target in targets if isinstance(target, ast.Name))


def test_no_global_mutable_registries_or_service_locators() -> None:
    """Module-level mutable registry/service/plugin/locator を作らない。"""
    violations: list[str] = []
    for path in _target_files():
        tree = parse_python_file(path)
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
                continue
            if not _is_mutable_literal(node.value):
                continue
            names = _assigned_names(node)
            if any(part in name.lower() for name in names for part in TARGET_NAME_PARTS):
                violations.append(f"{path}:{node.lineno}: {', '.join(names)}")
    assert not violations, "\n".join(violations)
