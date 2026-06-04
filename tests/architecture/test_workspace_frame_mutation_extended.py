"""Extended architecture guard against WorkspaceFrame mutation."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCAN_ROOTS: tuple[Path, ...] = (
    Path("iris/cognitive"),
    Path("iris/features"),
)

EXCLUDED_FILES: frozenset[Path] = frozenset(
    {
        Path("iris/cognitive/workspace/frame.py"),
        Path("iris/cognitive/cycle/frame_builder.py"),
        Path("iris/cognitive/cycle/models.py"),
    }
)


def _python_files() -> tuple[Path, ...]:
    """Return files that must not mutate WorkspaceFrame instances."""
    files: list[Path] = []
    for root in SCAN_ROOTS:
        base = PROJECT_ROOT / root
        if base.is_dir():
            files.extend(path for path in base.rglob("*.py") if path.relative_to(PROJECT_ROOT) not in EXCLUDED_FILES)
    return tuple(sorted(files))


def _is_frame_attribute(target: ast.AST) -> bool:
    """Return whether an AST target accesses frame.<attribute>."""
    return (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "frame"
    )


def _is_frame_collection_mutator(node: ast.Call) -> bool:
    """Return whether a call mutates a collection hanging from frame."""
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr in {"append", "extend", "insert", "remove", "pop", "clear", "update", "setdefault"}
        and isinstance(node.func.value, ast.Attribute)
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "frame"
    )


def _is_object_setattr_on_frame(node: ast.Call) -> bool:
    """Return whether a call invokes object.__setattr__(frame, ...)."""
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "__setattr__"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "object"
        and bool(node.args)
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "frame"
    )


def test_workspace_frame_is_not_mutated_by_steps_or_features() -> None:
    """Pipeline steps and features must return typed results instead of mutating frame."""
    violations: list[str] = []

    for path in _python_files():
        rel_path = path.relative_to(PROJECT_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if _is_frame_attribute(target):
                        violations.append(f"{rel_path}:{node.lineno}: assignment to frame attribute")
            elif isinstance(node, ast.AugAssign) and _is_frame_attribute(node.target):
                violations.append(f"{rel_path}:{node.lineno}: augmented assignment to frame attribute")
            elif isinstance(node, ast.Delete):
                for target in node.targets:
                    if _is_frame_attribute(target):
                        violations.append(f"{rel_path}:{node.lineno}: delete frame attribute")
            elif isinstance(node, ast.Call):
                if _is_frame_collection_mutator(node):
                    violations.append(f"{rel_path}:{node.lineno}: mutates collection on frame")
                if _is_object_setattr_on_frame(node):
                    violations.append(f"{rel_path}:{node.lineno}: object.__setattr__(frame, ...)")

    assert not violations, "WorkspaceFrame mutation violations:\n" + "\n".join(violations)
