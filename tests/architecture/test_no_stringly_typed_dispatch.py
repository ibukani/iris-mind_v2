"""Internal behavior の stringly typed dispatch を禁止する。"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from tests.architecture.helpers.ast_utils import parse_python_file
from tests.architecture.helpers.project_paths import IRIS_ROOT

if TYPE_CHECKING:
    from pathlib import Path

TARGET_ROOTS = (
    IRIS_ROOT / "cognitive",
    IRIS_ROOT / "runtime",
    IRIS_ROOT / "features",
)

EXCLUDED_ROOTS = (IRIS_ROOT / "runtime/config",)

DISPATCH_ATTRS = {"action", "type", "kind"}


def _target_files() -> tuple[Path, ...]:
    files: list[Path] = []
    for root in TARGET_ROOTS:
        files.extend(root.rglob("*.py"))
    return tuple(
        path
        for path in sorted(files)
        if not any(path.is_relative_to(root) for root in EXCLUDED_ROOTS)
    )


def _is_dispatch_attr(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr in DISPATCH_ATTRS


def _has_string_comparator(node: ast.Compare) -> bool:
    return any(
        isinstance(item, ast.Constant) and isinstance(item.value, str) for item in node.comparators
    )


def _match_case_is_string_value(case: ast.match_case) -> bool:
    return (
        isinstance(case.pattern, ast.MatchValue)
        and isinstance(case.pattern.value, ast.Constant)
        and isinstance(case.pattern.value.value, str)
    )


def test_internal_layers_do_not_branch_on_string_action_type_or_kind() -> None:
    """action/type/kind の文字列比較で内部 behavior を分岐しない。"""
    violations: list[str] = []
    for path in _target_files():
        for node in ast.walk(parse_python_file(path)):
            if (
                isinstance(node, ast.Compare)
                and _is_dispatch_attr(node.left)
                and _has_string_comparator(node)
            ):
                violations.append(f"{path}:{node.lineno}: string dispatch compare")
            elif isinstance(node, ast.Match) and _is_dispatch_attr(node.subject):
                for case in node.cases:
                    if _match_case_is_string_value(case):
                        location = f"{path}:{case.pattern.lineno}"
                        violations.append(f"{location}: string dispatch match")
    assert not violations, "\n".join(violations)
