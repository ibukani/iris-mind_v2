"""Coordinator で concrete Observation subclass routing を禁止する。"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from tests.architecture.helpers.ast_utils import name_of, parse_python_file
from tests.architecture.helpers.project_paths import PROJECT_ROOT

if TYPE_CHECKING:
    from pathlib import Path

COORDINATOR_FILES = (
    "iris/runtime/service.py",
    "iris/runtime/app.py",
    "iris/cognitive/cycle/service.py",
)


def _observation_subclasses() -> set[str]:
    tree = parse_python_file(PROJECT_ROOT / "iris/contracts/observations.py")
    concrete: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name == "Observation":
            continue
        base_names = {name_of(base) for base in node.bases}
        if "Observation" in base_names or any(
            name is not None and name.endswith("Observation") for name in base_names
        ):
            concrete.add(node.name)
    return concrete


def _is_observation_name(node: ast.AST, concrete: set[str]) -> bool:
    return name_of(node) in concrete


def _contains_observation_name(node: ast.AST, concrete: set[str]) -> bool:
    """Node が concrete Observation 名を直接または tuple 内に含むか。

    Returns:
        含む場合 True。
    """
    if _is_observation_name(node, concrete):
        return True
    if isinstance(node, ast.Tuple):
        return any(_contains_observation_name(elt, concrete) for elt in node.elts)
    return False


def _branching_violations(path: Path, concrete: set[str]) -> list[str]:
    tree = parse_python_file(path)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and name_of(node.func) == "isinstance":
            if len(node.args) >= 2 and _contains_observation_name(node.args[1], concrete):
                violations.append(f"{path}:{node.lineno}: isinstance concrete Observation")
        elif isinstance(node, ast.Compare) and _is_type_observation_compare(node, concrete):
            violations.append(f"{path}:{node.lineno}: type(...) concrete Observation compare")
        elif isinstance(node, ast.MatchClass) and _is_observation_name(node.cls, concrete):
            violations.append(f"{path}:{node.lineno}: match concrete Observation")
    return violations


def _is_type_observation_compare(node: ast.Compare, concrete: set[str]) -> bool:
    if not (
        isinstance(node.left, ast.Call)
        and name_of(node.left.func) == "type"
        and len(node.left.args) == 1
    ):
        return False
    return any(_is_observation_name(comparator, concrete) for comparator in node.comparators)


def test_coordinators_do_not_route_by_concrete_observation_types() -> None:
    """Coordinator は concrete Observation subclass で分岐しない。"""
    concrete = _observation_subclasses()
    violations: list[str] = []
    for relative_path in COORDINATOR_FILES:
        violations.extend(_branching_violations(PROJECT_ROOT / relative_path, concrete))
    assert not violations, "\n".join(violations)
