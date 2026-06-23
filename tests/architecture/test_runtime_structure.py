"""Runtime placement guards for orchestration-only structure."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RUNTIME_ROOT = PROJECT_ROOT / "iris" / "runtime"
EVENT_REACTION_FEATURE_ROOT = PROJECT_ROOT / "iris" / "features" / "event_reaction"
EVENT_REACTION_PRESENTATION = PROJECT_ROOT / "iris" / "presentation" / "event_reaction.py"

ALLOWED_RUNTIME_PACKAGE_DIRS: frozenset[str] = frozenset(
    {
        "config",
        "delivery",
        "ingress",
        "lifecycle",
        "observability",
        "scheduler",
        "state",
        "wiring",
    },
)

EVENT_REACTION_FEATURE_FORBIDDEN_IMPORTS: frozenset[str] = frozenset(
    {
        "iris.adapters",
        "iris.presentation",
        "iris.runtime",
        "iris.safety",
    },
)

EVENT_REACTION_PRESENTATION_FORBIDDEN_IMPORTS: frozenset[str] = frozenset(
    {
        "iris.adapters",
        "iris.features",
        "iris.runtime",
        "iris.safety",
    },
)

FORBIDDEN_RUNTIME_FEATURE_LOGIC_NAMES: frozenset[str] = frozenset(
    {
        "planner.py",
        "policy.py",
        "templates.py",
    },
)


def _python_files(root: Path) -> tuple[Path, ...]:
    """Return Python files under an existing root."""
    if not root.is_dir():
        return ()
    return tuple(sorted(root.rglob("*.py")))


def _imports(path: Path) -> tuple[str, ...]:
    """Return import module names found in a Python file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
    return tuple(imports)


def _forbidden_import_violations(
    root: Path,
    forbidden_prefixes: frozenset[str],
) -> list[str]:
    """Return forbidden import violations under root."""
    violations: list[str] = []
    for path in _python_files(root):
        rel_path = path.relative_to(PROJECT_ROOT).as_posix()
        violations.extend(
            f"{rel_path}: imports {imported}"
            for imported in _imports(path)
            for forbidden in forbidden_prefixes
            if imported.startswith(forbidden)
        )
    return violations


def test_runtime_top_level_package_dirs_are_allowlisted() -> None:
    """runtime直下のpackage directoryを明示allowlistに限定する。"""
    package_dirs = {
        path.name
        for path in RUNTIME_ROOT.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    }

    unexpected = sorted(package_dirs - ALLOWED_RUNTIME_PACKAGE_DIRS)

    assert not unexpected, "runtime top-level packages need architecture approval: " + ", ".join(
        unexpected,
    )


def test_event_reaction_feature_does_not_import_outer_layers() -> None:
    """event_reaction feature logic must stay independent from runtime and output layers."""
    violations = _forbidden_import_violations(
        EVENT_REACTION_FEATURE_ROOT,
        EVENT_REACTION_FEATURE_FORBIDDEN_IMPORTS,
    )

    assert not violations, "event reaction feature imports forbidden layers:\n" + "\n".join(
        violations,
    )


def test_event_reaction_presentation_does_not_import_feature_or_runtime_layers() -> None:
    """event_reaction presentation must remain a thin candidate-to-output converter."""
    violations = [
        f"{EVENT_REACTION_PRESENTATION.relative_to(PROJECT_ROOT).as_posix()}: imports {imported}"
        for imported in _imports(EVENT_REACTION_PRESENTATION)
        for forbidden in EVENT_REACTION_PRESENTATION_FORBIDDEN_IMPORTS
        if imported.startswith(forbidden)
    ]

    assert not violations, "event reaction presentation imports forbidden layers:\n" + "\n".join(
        violations,
    )


def test_runtime_does_not_own_event_reaction_planning_or_templates() -> None:
    """runtime配下へfeature-specific planning/template moduleを戻さない。"""
    violations = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in _python_files(RUNTIME_ROOT)
        if "event_reaction" in path.parts and path.name in FORBIDDEN_RUNTIME_FEATURE_LOGIC_NAMES
    ]

    assert not violations, "event reaction feature logic belongs in iris/features:\n" + "\n".join(
        violations,
    )
