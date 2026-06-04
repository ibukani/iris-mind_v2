"""Extended architecture guard against service locator escape hatches."""

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
    Path("iris/adapters"),
    Path("iris/runtime"),
)

FORBIDDEN_IMPORT_PREFIXES: frozenset[str] = frozenset(
    {
        "dependency_injector",
        "injector",
        "punq",
        "lagom",
    }
)

FORBIDDEN_CALL_PARTS: frozenset[str] = frozenset(
    {
        "resolve",
        "resolve_optional",
        "resolve_all",
        "get_service",
        "locate",
        "inject",
    }
)

FORBIDDEN_TEXT_PATTERNS: frozenset[str] = frozenset(
    {
        "ServiceLocator",
        "ServiceProvider",
        "GlobalRegistry",
        "providers.Container",
        "dependency_injector",
        "resolve_optional(",
        "resolve_all(",
        ".resolve_optional(",
        ".resolve_all(",
        ".get_service(",
        ".locate(",
        ".inject(",
    }
)


def _python_files() -> tuple[Path, ...]:
    """Return source Python files checked for service locator patterns."""
    files: list[Path] = []
    for root in SOURCE_ROOTS:
        base = PROJECT_ROOT / root
        if base.is_dir():
            files.extend(base.rglob("*.py"))
    return tuple(sorted(files))


def _imports(tree: ast.Module) -> tuple[str, ...]:
    """Return imports found in a module."""
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
    return tuple(imports)


def _call_name_parts(node: ast.Call) -> tuple[str, ...]:
    """Return dotted call name parts for a call node."""
    parts: list[str] = []
    current = node.func
    while isinstance(current, ast.Attribute):
        parts.insert(0, current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.insert(0, current.id)
    return tuple(parts)


def test_extended_service_locator_patterns_are_forbidden() -> None:
    """Source modules must not reintroduce broader service locator patterns."""
    violations: list[str] = []

    for path in _python_files():
        rel_path = path.relative_to(PROJECT_ROOT)
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))

        for imported in _imports(tree):
            if any(imported.startswith(prefix) for prefix in FORBIDDEN_IMPORT_PREFIXES):
                violations.append(f"{rel_path}: imports {imported}")

        for pattern in FORBIDDEN_TEXT_PATTERNS:
            if pattern in text:
                violations.append(f"{rel_path}: contains {pattern!r}")

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            parts = _call_name_parts(node)
            if any(part in FORBIDDEN_CALL_PARTS for part in parts):
                if parts == ("TypeVar", "resolve"):
                    continue
                violations.append(f"{rel_path}:{node.lineno}: calls {'.'.join(parts)}")

    assert not violations, "extended service locator patterns found:\n" + "\n".join(violations)
