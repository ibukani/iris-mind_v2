"""Architecture guard ensuring CognitiveCycle remains a pure coordinator."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SERVICE_PATH = PROJECT_ROOT / "iris" / "cognitive" / "cycle" / "service.py"

FORBIDDEN_CALL_PARTS: frozenset[str] = frozenset(
    {
        "chat",
        "complete",
        "generate",
        "search",
        "retrieve",
        "save",
        "store",
        "present",
        "check_plan",
        "check_output",
        "send",
        "execute",
        "publish",
    }
)

ALLOWED_CALL_NAMES: frozenset[str] = frozenset(
    {
        "WorkspaceFrame",
        "step.run",
        "self._frame_builder.apply",
        "self._select_action_plan",
        "CycleResult",
    }
)


def _find_class(tree: ast.Module, class_name: str) -> ast.ClassDef:
    """Locate a class node by name in a parsed module.

    Args:
        tree: Parsed module AST to search.
        class_name: Class name to locate.

    Returns:
        ast.ClassDef: The matching class definition node.

    Raises:
        AssertionError: If the class is not present in the tree.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    message = f"{class_name} not found"
    raise AssertionError(message)


def _find_method(
    class_node: ast.ClassDef,
    method_name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """Locate a method node by name on a class body.

    Args:
        class_node: Class definition node to search.
        method_name: Method name to locate.

    Returns:
        ast.FunctionDef | ast.AsyncFunctionDef: The matching method node.

    Raises:
        AssertionError: If the method is not declared on the class.
    """
    for node in class_node.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name:
            return node
    message = f"{class_node.name}.{method_name} not found"
    raise AssertionError(message)


def _call_name(node: ast.Call) -> str:
    """Return a dotted call name."""
    parts: list[str] = []
    current = node.func
    while isinstance(current, ast.Attribute):
        parts.insert(0, current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.insert(0, current.id)
    return ".".join(parts)


def test_cognitive_cycle_run_contains_only_coordination_calls() -> None:
    """CognitiveCycle.run must not grow LLM, memory, safety, or presentation work."""
    tree = ast.parse(SERVICE_PATH.read_text(encoding="utf-8"), filename=str(SERVICE_PATH))
    cycle_class = _find_class(tree, "CognitiveCycle")
    run_method = _find_method(cycle_class, "run")

    violations: list[str] = []
    for node in ast.walk(run_method):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name in ALLOWED_CALL_NAMES:
            continue
        if any(part in FORBIDDEN_CALL_PARTS for part in name.split(".")):
            violations.append(
                f"{SERVICE_PATH.relative_to(PROJECT_ROOT)}:{node.lineno}: calls {name}"
            )

    assert not violations, "CognitiveCycle.run contains non-coordinator calls:\n" + "\n".join(
        violations,
    )
