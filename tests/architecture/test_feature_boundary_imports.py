"""Architecture guards for feature-to-cognitive import boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FEATURES_ROOT = PROJECT_ROOT / "iris" / "features"

ALLOWED_COGNITIVE_IMPORTS: frozenset[tuple[Path, str]] = frozenset(
    {
        (
            Path("iris/features/definition.py"),
            "iris.cognitive.cycle",
        ),
        (
            Path("iris/features/proactive_talk/definition.py"),
            "iris.cognitive.cycle.models",
        ),
        (
            Path("iris/features/proactive_talk/definition.py"),
            "iris.cognitive.cycle.pipeline",
        ),
        (
            Path("iris/features/proactive_talk/definition.py"),
            "iris.cognitive.workspace.frame",
        ),
    }
)


def _python_files() -> tuple[Path, ...]:
    """Return feature Python files."""
    if not FEATURES_ROOT.is_dir():
        return ()
    return tuple(sorted(FEATURES_ROOT.rglob("*.py")))


def _imports(path: Path) -> tuple[str, ...]:
    """Return imports found in a Python file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
    return tuple(imports)


def _is_allowed(rel_path: Path, imported: str) -> bool:
    """Return whether a cognitive import is an explicit feature-boundary exception."""
    return any(
        rel_path == allowed_path and imported.startswith(allowed_prefix)
        for allowed_path, allowed_prefix in ALLOWED_COGNITIVE_IMPORTS
    )


def test_features_do_not_import_cognitive_internals_without_explicit_exception() -> None:
    """Feature slices must not reach into cognitive internals by default."""
    violations: list[str] = []

    for path in _python_files():
        rel_path = path.relative_to(PROJECT_ROOT)
        for imported in _imports(path):
            if not imported.startswith("iris.cognitive"):
                continue
            if _is_allowed(rel_path, imported):
                continue
            violations.append(f"{rel_path}: imports {imported}")

    assert not violations, "feature-to-cognitive import violations:\n" + "\n".join(violations)
