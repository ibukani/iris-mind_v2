"""Architecture guard: async work must have an explicit lifecycle owner."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCAN_ROOTS: tuple[str, ...] = ("iris", "tests", "scripts")
EXCLUDED_ROOTS: frozenset[str] = frozenset({"iris/generated"})
ALLOWED_EVENT_LOOP_CONTROLS: frozenset[tuple[str, int, str]] = frozenset(
    {
        ("iris/runtime/server.py", 285, "asyncio.run"),
    }
)


@dataclass(frozen=True)
class _AsyncFinding:
    path: str
    line: int
    call: str


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


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        if base is None:
            return node.attr
        return f"{base}.{node.attr}"
    return None


def _is_untracked_task_call(node: ast.Call) -> str | None:
    name = _call_name(node.func)
    if name in {"asyncio.create_task", "asyncio.ensure_future"}:
        return name
    if isinstance(node.func, ast.Attribute) and node.func.attr == "create_task":
        return "loop.create_task"
    return None


def _is_event_loop_control(node: ast.Call) -> str | None:
    name = _call_name(node.func)
    if name == "asyncio.run":
        return name
    if isinstance(node.func, ast.Attribute) and node.func.attr == "run_until_complete":
        return "loop.run_until_complete"
    return None


def _collect_async_findings(path: Path) -> tuple[_AsyncFinding, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rel_path = _relative_path(path)
    findings: list[_AsyncFinding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call_name = _is_untracked_task_call(node.value)
            if call_name is not None:
                findings.append(_AsyncFinding(rel_path, node.lineno, call_name))
        if rel_path.startswith("iris/") and isinstance(node, ast.Call):
            call_name = _is_event_loop_control(node)
            if call_name is not None:
                findings.append(_AsyncFinding(rel_path, node.lineno, call_name))
    return tuple(findings)


def test_async_tasks_are_not_created_without_lifecycle_owner() -> None:
    """Fire-and-forget async tasks must not be introduced."""
    violations: list[str] = []
    for path in _python_files():
        violations.extend(
            f"{finding.path}:{finding.line}: {finding.call}"
            for finding in _collect_async_findings(path)
            if finding.call in {"asyncio.create_task", "asyncio.ensure_future", "loop.create_task"}
        )

    assert not violations, "".join(
        (
            "Async tasks must be awaited, stored in a lifecycle owner, ",
            "or managed by a task group:\n",
            "\n".join(violations),
        )
    )


def test_production_code_does_not_control_nested_event_loops() -> None:
    """Production internals must not control nested event loops."""
    violations: list[str] = []
    for path in _python_files():
        for finding in _collect_async_findings(path):
            key = (finding.path, finding.line, finding.call)
            if finding.call in {"asyncio.run", "loop.run_until_complete"} and (
                key not in ALLOWED_EVENT_LOOP_CONTROLS
            ):
                violations.append(f"{finding.path}:{finding.line}: {finding.call}")

    assert not violations, "".join(
        (
            "Do not control event loops inside iris/ internals. ",
            "Keep asyncio.run in CLI/script entrypoints only:\n",
            "\n".join(violations),
        )
    )
