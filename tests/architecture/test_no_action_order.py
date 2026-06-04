"""Architecture guard for no-action runtime short-circuit ordering."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
APP_PATH = PROJECT_ROOT / "iris" / "runtime" / "app.py"


def _find_method(class_node: ast.ClassDef, method_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """Find a method on a class."""
    for node in class_node.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name:
            return node
    message = f"{class_node.name}.{method_name} not found"
    raise AssertionError(message)


def _find_class(tree: ast.Module, class_name: str) -> ast.ClassDef:
    """Find a class in a module."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    message = f"{class_name} not found"
    raise AssertionError(message)


def _node_mentions_text(node: ast.AST, text: str) -> bool:
    """Return whether an AST node's source-ish representation contains text."""
    return text in ast.unparse(node)


def _first_statement_index(method: ast.FunctionDef | ast.AsyncFunctionDef, text: str) -> int:
    """Return first top-level statement index containing text."""
    for index, statement in enumerate(method.body):
        if _node_mentions_text(statement, text):
            return index
    message = f"{text!r} not found in {method.name}"
    raise AssertionError(message)


def _no_action_if_statement(method: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.If:
    """Return the top-level if statement checking plan.is_no_action."""
    for statement in method.body:
        if isinstance(statement, ast.If) and _node_mentions_text(statement.test, "is_no_action"):
            return statement
    msg = "process_observation must have a top-level plan.is_no_action guard"
    raise AssertionError(msg)


def test_no_action_guard_precedes_safety_presentation_and_output_gates() -> None:
    """No-action must short-circuit before safety, presentation, or output gates run."""
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"), filename=str(APP_PATH))
    app_class = _find_class(tree, "IrisApp")
    method = _find_method(app_class, "process_observation")

    no_action_index = _first_statement_index(method, "is_no_action")
    check_plan_index = _first_statement_index(method, "check_plan")
    present_index = _first_statement_index(method, "present")
    check_output_index = _first_statement_index(method, "check_output")

    assert no_action_index < check_plan_index < present_index < check_output_index


def test_no_action_branch_returns_empty_presented_output_only() -> None:
    """The no-action branch must not call downstream gates or presenter methods."""
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"), filename=str(APP_PATH))
    app_class = _find_class(tree, "IrisApp")
    method = _find_method(app_class, "process_observation")
    no_action_guard = _no_action_if_statement(method)

    branch_text = "\n".join(ast.unparse(statement) for statement in no_action_guard.body)
    assert "PresentedOutput(text=None)" in branch_text
    assert "check_plan" not in branch_text
    assert "present" not in branch_text
    assert "check_output" not in branch_text
    assert "run(" not in branch_text
