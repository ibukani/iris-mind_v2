"""Internal layers で untyped dictionary boundary を禁止する。"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from tests.architecture.helpers.ast_utils import name_of, parse_python_file
from tests.architecture.helpers.project_paths import IRIS_ROOT

if TYPE_CHECKING:
    from pathlib import Path

TARGET_LAYERS = (
    "contracts",
    "core",
    "cognitive",
    "features",
    "presentation",
    "safety",
    "runtime",
)

FORBIDDEN_CONTAINER_NAMES = {"dict", "Dict", "Mapping", "MutableMapping"}


def _target_files() -> tuple[Path, ...]:
    files: list[Path] = []
    for layer in TARGET_LAYERS:
        files.extend((IRIS_ROOT / layer).rglob("*.py"))
    return tuple(sorted(files))


def _slice_names(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Tuple):
        return tuple(name_of(elt) or "" for elt in node.elts)
    return (name_of(node) or "",)


def _is_forbidden_annotation(node: ast.AST) -> bool:
    if isinstance(node, ast.Subscript):
        container = name_of(node.value)
        names = _slice_names(node.slice)
        if container in FORBIDDEN_CONTAINER_NAMES and len(names) >= 2 and names[0] == "str":
            return names[1] in {"Any", "object"}
        return container == "Callable" and "Any" in names and "Ellipsis" in names
    return False


def test_internal_layers_do_not_expose_untyped_boundaries() -> None:
    """Internal layer annotation に dict[str, Any] などを入れない。"""
    violations: list[str] = []
    for path in _target_files():
        for node in ast.walk(parse_python_file(path)):
            annotation = getattr(node, "annotation", None)
            if isinstance(annotation, ast.AST) and _is_forbidden_annotation(annotation):
                line_number = getattr(node, "lineno", 0)
                violations.append(f"{path}:{line_number}: {ast.unparse(annotation)}")
    assert not violations, "\n".join(violations)
