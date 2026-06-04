"""Extended architecture guard against module-level mutable state."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE_ROOTS: tuple[Path, ...] = (
    Path("iris/contracts"),
    Path("iris/core"),
    Path("iris/cognitive"),
    Path("iris/features"),
    Path("iris/presentation"),
    Path("iris/safety"),
    Path("iris/runtime"),
)

SUSPICIOUS_NAMES: frozenset[str] = frozenset(
    {
        "registry",
        "registries",
        "container",
        "containers",
        "cache",
        "caches",
        "handlers",
        "listeners",
    }
)

MUTABLE_CONSTRUCTORS: frozenset[str] = frozenset({"dict", "list", "set", "defaultdict"})


def _python_files() -> tuple[Path, ...]:
    """Return protected source files."""
    files: list[Path] = []
    for root in SOURCE_ROOTS:
        base = PROJECT_ROOT / root
        if base.is_dir():
            files.extend(base.rglob("*.py"))
    return tuple(sorted(files))


def _value_is_mutable(value: ast.AST | None) -> bool:
    """Return whether a value is a mutable literal or constructor call."""
    if isinstance(value, (ast.Dict, ast.List, ast.Set)):
        return True
    if isinstance(value, ast.Call):
        func = value.func
        if isinstance(func, ast.Name) and func.id in MUTABLE_CONSTRUCTORS:
            return True
        if isinstance(func, ast.Attribute) and func.attr in MUTABLE_CONSTRUCTORS:
            return True
    return False


def _name_is_suspicious(name: str) -> bool:
    """Return whether a name suggests hidden mutable module state."""
    lowered = name.lower().lstrip("_")
    return lowered in SUSPICIOUS_NAMES or any(
        lowered.endswith(f"_{suffix}") for suffix in SUSPICIOUS_NAMES
    )


def _violation_for_assign(node: ast.Assign, rel_path: Path) -> list[str]:
    """Return violation strings for a plain assignment node, when mutable and suspicious."""
    found: list[str] = []
    for target in node.targets:
        if not isinstance(target, ast.Name):
            continue
        if _value_is_mutable(node.value) and _name_is_suspicious(target.id):
            found.append(f"{rel_path}:{node.lineno}: {target.id}")
    return found


def _violation_for_annassign(node: ast.AnnAssign, rel_path: Path) -> list[str]:
    """Return violation strings for an annotated assignment node, when mutable and suspicious."""
    if not isinstance(node.target, ast.Name):
        return []
    if _value_is_mutable(node.value) and _name_is_suspicious(node.target.id):
        return [f"{rel_path}:{node.lineno}: {node.target.id}"]
    return []


def test_no_suspicious_module_level_mutable_state_in_protected_layers() -> None:
    """Protected source layers must avoid hidden module-level mutable state."""
    violations: list[str] = []

    for path in _python_files():
        rel_path = path.relative_to(PROJECT_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                violations.extend(_violation_for_assign(node, rel_path))
            elif isinstance(node, ast.AnnAssign):
                violations.extend(_violation_for_annassign(node, rel_path))

    assert not violations, "suspicious module-level mutable state found:\n" + "\n".join(
        violations,
    )
