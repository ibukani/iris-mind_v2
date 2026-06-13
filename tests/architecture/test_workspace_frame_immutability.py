"""WorkspaceFrame の直接 mutation を禁止する。"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from tests.architecture.helpers.ast_utils import name_of, parse_python_file
from tests.architecture.helpers.project_paths import PROJECT_ROOT

if TYPE_CHECKING:
    from pathlib import Path

APPROVED_PATHS = {
    PROJECT_ROOT / "iris/cognitive/cycle/frame_builder.py",
    PROJECT_ROOT / "iris/cognitive/workspace/frame.py",
}

MUTATING_METHODS = {
    "append",
    "extend",
    "insert",
    "pop",
    "remove",
    "clear",
    "update",
    "setdefault",
}


def _target_files() -> tuple[Path, ...]:
    root = PROJECT_ROOT / "iris/cognitive"
    return tuple(path for path in sorted(root.rglob("*.py")) if path not in APPROVED_PATHS)


def _is_frame_attribute(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "frame"
    )


def test_workspace_frame_is_not_mutated_directly() -> None:
    """Approved path 以外では frame field を直接変更しない。"""
    violations: list[str] = []
    for path in _target_files():
        for node in ast.walk(parse_python_file(path)):
            if isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(_is_frame_attribute(target) for target in targets):
                    violations.append(f"{path}:{node.lineno}: frame attribute assignment")
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and name_of(node.func) in MUTATING_METHODS
                and _is_frame_attribute(node.func.value)
            ):
                violations.append(f"{path}:{node.lineno}: frame mutating method")
            elif isinstance(node, ast.Call) and name_of(node.func) == "__setattr__":
                violations.append(f"{path}:{node.lineno}: object.__setattr__")
    assert not violations, "\n".join(violations)
