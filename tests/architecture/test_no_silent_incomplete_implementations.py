"""Architecture guard against silent incomplete implementation markers."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TypeGuard

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE_ROOT = PROJECT_ROOT / "iris"

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def _source_files() -> tuple[Path, ...]:
    """Return Iris source files checked by this architecture guard."""
    return tuple(sorted(SOURCE_ROOT.rglob("*.py")))


def _scan_file(path: Path) -> list[str]:
    """Return silent incomplete implementation violations for one source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    allowed_ellipsis_ids = _allowed_ellipsis_expr_ids(tree)
    rel_path = path.relative_to(PROJECT_ROOT)
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Pass):
            violations.append(f"{rel_path}:{node.lineno}: pass hides an incomplete implementation")
        if _is_forbidden_ellipsis(node, allowed_ellipsis_ids):
            violations.append(
                f"{rel_path}:{node.lineno}: ellipsis is only allowed in explicit stubs"
            )
        if isinstance(node, ast.Raise) and _is_bare_not_implemented(node):
            violations.append(
                f"{rel_path}:{node.lineno}: NotImplementedError must include a message"
            )

    return violations


def _allowed_ellipsis_expr_ids(tree: ast.AST) -> set[int]:
    """Return ellipsis expression ids allowed by Protocol or abstract stubs."""
    allowed: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _is_protocol_class(node):
            allowed.update(_protocol_ellipsis_expr_ids(node))
        if isinstance(node, FunctionNode) and _is_abstract_function(node):
            allowed.update(_ellipsis_expr_ids(node.body))
    return allowed


def _protocol_ellipsis_expr_ids(node: ast.ClassDef) -> set[int]:
    """Return ellipsis expression ids in direct Protocol method bodies."""
    allowed: set[int] = set()
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            allowed.update(_ellipsis_expr_ids(item.body))
    return allowed


def _ellipsis_expr_ids(statements: list[ast.stmt]) -> set[int]:
    """Return ellipsis expression ids from a statement sequence."""
    return {
        id(statement)
        for statement in statements
        if isinstance(statement, ast.Expr) and _is_ellipsis_expr(statement)
    }


def _is_forbidden_ellipsis(node: ast.AST, allowed_ellipsis_ids: set[int]) -> TypeGuard[ast.Expr]:
    """Return whether an ellipsis expression is outside an explicit stub context."""
    return (
        isinstance(node, ast.Expr)
        and _is_ellipsis_expr(node)
        and id(node) not in allowed_ellipsis_ids
    )


def _is_protocol_class(node: ast.ClassDef) -> bool:
    """Return whether a class directly declares Protocol as a base."""
    return any(_base_name(base) == "Protocol" for base in node.bases)


def _base_name(node: ast.expr) -> str | None:
    """Return the simple name represented by a base expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    return None


def _is_abstract_function(node: FunctionNode) -> bool:
    """Return whether a function is decorated with abstractmethod."""
    return any(_decorator_name(decorator) == "abstractmethod" for decorator in node.decorator_list)


def _decorator_name(node: ast.expr) -> str | None:
    """Return the simple name represented by a decorator expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return None


def _is_ellipsis_expr(node: ast.Expr) -> bool:
    """Return whether an expression statement is a literal ellipsis."""
    return isinstance(node.value, ast.Constant) and node.value.value is Ellipsis


def _is_bare_not_implemented(node: ast.Raise) -> bool:
    """Return whether a raise uses NotImplementedError without a message."""
    exc = node.exc
    if isinstance(exc, ast.Name):
        return exc.id == "NotImplementedError"
    if isinstance(exc, ast.Call):
        return _call_name(exc) == "NotImplementedError" and not exc.args
    return False


def _call_name(node: ast.Call) -> str | None:
    """Return the simple callable name for a call expression."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def test_no_silent_incomplete_implementations_in_iris_source() -> None:
    """Incomplete implementations must be explicit, typed, and reviewable."""
    violations: list[str] = []
    for path in _source_files():
        violations.extend(_scan_file(path))

    message = "silent incomplete implementation markers are forbidden:\n" + "\n".join(violations)
    assert not violations, message
