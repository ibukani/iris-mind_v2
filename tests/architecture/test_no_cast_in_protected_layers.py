"""Architecture guard against cast-based type fixes in protected layers."""

from __future__ import annotations

import ast
from pathlib import Path

PROTECTED_ROOTS: tuple[Path, ...] = (
    Path("iris/contracts"),
    Path("iris/core"),
    Path("iris/cognitive"),
    Path("iris/features"),
    Path("iris/presentation"),
    Path("iris/safety"),
    Path("iris/runtime"),
)

ALLOWED_CAST_FILES: frozenset[Path] = frozenset()


def _python_files() -> tuple[Path, ...]:
    """Return protected Python files checked by this architecture guard."""
    files: list[Path] = []
    for root in PROTECTED_ROOTS:
        files.extend(path for path in root.rglob("*.py") if path not in ALLOWED_CAST_FILES)
    return tuple(sorted(files))


def _is_cast_call(node: ast.Call) -> bool:
    """Return whether an AST call invokes typing.cast or an imported cast alias."""
    match node.func:
        case ast.Name(id="cast"):
            return True
        case ast.Attribute(attr="cast"):
            return True
        case _:
            return False


def test_typing_cast_is_not_used_in_protected_architecture_layers() -> None:
    """Protected layers must fix typing at the boundary instead of using casts."""
    violations: list[str] = []

    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        violations.extend(
            f"{path}:{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and _is_cast_call(node)
        )

    assert not violations, "typing.cast is forbidden in protected layers:\n" + "\n".join(
        violations,
    )
