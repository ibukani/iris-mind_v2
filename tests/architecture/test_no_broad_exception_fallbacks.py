"""Architecture guard: broad exceptions must not hide default fallbacks."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCAN_ROOTS: tuple[str, ...] = ("iris", "tests", "scripts")
EXCLUDED_ROOTS: frozenset[str] = frozenset({"iris/generated"})


@dataclass(frozen=True)
class _BroadFallback:
    path: str
    line: int
    reason: str


def _relative_path(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _is_excluded(path: Path) -> bool:
    rel_path = _relative_path(path)
    return any(
        rel_path == excluded or rel_path.startswith(f"{excluded}/") for excluded in EXCLUDED_ROOTS
    )


def _python_files() -> tuple[Path, ...]:
    paths: list[Path] = []
    for root in SCAN_ROOTS:
        paths.extend(path for path in (PROJECT_ROOT / root).rglob("*.py") if not _is_excluded(path))
    return tuple(sorted(paths))


def _is_broad_exception_type(node: ast.AST | None) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.Name):
        return node.id in {"Exception", "BaseException"}
    if isinstance(node, ast.Tuple):
        return any(_is_broad_exception_type(item) for item in node.elts)
    return False


def _is_empty_collection(node: ast.AST) -> bool:
    return isinstance(node, (ast.List, ast.Dict, ast.Set, ast.Tuple)) and not (
        node.elts if isinstance(node, (ast.List, ast.Set, ast.Tuple)) else node.keys
    )


def _is_default_return(node: ast.Return) -> bool:
    value = node.value
    if value is None:
        return True
    if isinstance(value, ast.Constant):
        return value.value in {None, False, True, ""}
    return _is_empty_collection(value)


def _fallback_statement_reason(statement: ast.stmt) -> str | None:
    if isinstance(statement, ast.Pass):
        return "pass"
    if isinstance(statement, ast.Continue):
        return "continue"
    if isinstance(statement, ast.Return) and _is_default_return(statement):
        return "default return"
    return None


def _is_logging_call(node: ast.stmt) -> bool:
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    func = node.value.func
    return isinstance(func, ast.Attribute) and func.attr in {
        "debug",
        "info",
        "warning",
        "error",
        "exception",
        "critical",
        "log",
    }


def _fallback_reason(handler: ast.ExceptHandler) -> str | None:
    for statement in handler.body:
        reason = _fallback_statement_reason(statement)
        if reason is not None:
            return reason

    non_logging = [statement for statement in handler.body if not _is_logging_call(statement)]
    if (
        len(non_logging) == 1
        and isinstance(non_logging[0], ast.Return)
        and _is_default_return(non_logging[0])
    ):
        return "logging followed by default return"
    return None


def _collect_broad_exception_fallbacks(path: Path) -> tuple[_BroadFallback, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rel_path = _relative_path(path)
    findings: list[_BroadFallback] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not _is_broad_exception_type(node.type):
            continue
        reason = _fallback_reason(node)
        if reason is not None:
            findings.append(_BroadFallback(rel_path, node.lineno, reason))
    return tuple(findings)


def test_broad_exceptions_do_not_silently_return_defaults() -> None:
    """Broad exception handlers must fail loudly or raise domain errors."""
    violations: list[str] = []
    for path in _python_files():
        violations.extend(
            f"{finding.path}:{finding.line}: broad exception fallback ({finding.reason})"
            for finding in _collect_broad_exception_fallbacks(path)
        )

    assert not violations, "".join(
        (
            "Do not swallow broad exceptions with default fallbacks. ",
            "Raise, re-raise, or translate to a typed/domain exception:\n",
            "\n".join(violations),
        )
    )
