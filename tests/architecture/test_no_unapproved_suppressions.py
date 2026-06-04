"""Architecture guard against unapproved suppression escape hatches."""

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

ALLOWED_SUPPRESSION_LINES: frozenset[tuple[Path, int]] = frozenset()

SUPPRESSION_TOKENS: tuple[str, ...] = (
    "# noqa",
    "# type: ignore",
    "# pyright: ignore",
)


def _protected_python_files() -> tuple[Path, ...]:
    """Return protected Python files checked by this architecture guard."""
    files: list[Path] = []
    for root in PROTECTED_ROOTS:
        files.extend(root.rglob("*.py"))
    return tuple(sorted(files))


def _suppression_comment_violations(path: Path) -> list[str]:
    """Return suppression comment violations in a protected file."""
    violations: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if (path, line_number) in ALLOWED_SUPPRESSION_LINES:
            continue
        if any(token in line for token in SUPPRESSION_TOKENS):
            violations.append(f"{path}:{line_number}: {line.strip()}")
    return violations


def _is_object_setattr_call(node: ast.Call) -> bool:
    """Return whether an AST call invokes object.__setattr__."""
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "__setattr__"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "object"
    )


def _object_setattr_violations(path: Path) -> list[str]:
    """Return object.__setattr__ violations in a protected file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        f"{path}:{node.lineno}: object.__setattr__"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _is_object_setattr_call(node)
    ]


def test_no_unapproved_suppressions_in_protected_architecture_layers() -> None:
    """Protected layers must not use local suppressions to bypass quality gates."""
    violations: list[str] = []
    for path in _protected_python_files():
        violations.extend(_suppression_comment_violations(path))
        violations.extend(_object_setattr_violations(path))

    message = "unapproved suppressions are forbidden in protected layers:\n" + "\n".join(violations)
    assert not violations, message
