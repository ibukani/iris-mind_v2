"""Runtime placement guards for orchestration-only structure."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RUNTIME_ROOT = PROJECT_ROOT / "iris" / "runtime"
EVENT_REACTION_FEATURE_ROOT = PROJECT_ROOT / "iris" / "features" / "event_reaction"
EVENT_REACTION_PRESENTATION = PROJECT_ROOT / "iris" / "features" / "event_reaction" / "presenter.py"
EVENT_REACTION_RUNNER = PROJECT_ROOT / "iris" / "runtime" / "ingress" / "activity_event_reaction.py"

ALLOWED_RUNTIME_PACKAGE_DIRS: frozenset[str] = frozenset(
    {
        "auth",
        "config",
        "delivery",
        "ingress",
        "lifecycle",
        "learning",
        "local_ai",
        "observability",
        "scheduler",
        "state",
        "wiring",
    },
)

EVENT_REACTION_FEATURE_FORBIDDEN_IMPORTS: frozenset[str] = frozenset(
    {
        "iris.adapters",
        "iris.runtime",
        "iris.safety",
    },
)

EVENT_REACTION_PRESENTATION_FORBIDDEN_IMPORTS: frozenset[str] = frozenset(
    {
        "iris.features.event_reaction.planner",
        "iris.features.event_reaction.policy",
        "iris.features.event_reaction.templates",
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

RUNNER_FORBIDDEN_IMPORTS: frozenset[str] = frozenset(
    {
        "iris.contracts.activity",
        "iris.features.event_reaction.policy",
        "iris.features.event_reaction.templates",
    },
)

RUNNER_FORBIDDEN_NAMES: frozenset[str] = frozenset(
    {
        "ActivityKind",
        "EventReactionPolicy",
        "EventReactionTemplateProvider",
    },
)

RUNNER_FORBIDDEN_TEXT: frozenset[str] = frozenset(
    {
        "Welcome back",
    },
)

RUNTIME_SERVICE_FORBIDDEN_DIRECT_IMPORTS: frozenset[str] = frozenset(
    {
        "iris.adapters",
        "iris.features",
        "iris.presentation",
        "iris.runtime.delivery",
        "iris.runtime.lifecycle",
        "iris.runtime.observability.diagnostics",
        "iris.runtime.observability.events",
        "iris.runtime.observability.llm",
        "iris.runtime.observability.logger",
        "iris.runtime.scheduler",
        "iris.runtime.state",
    },
)
OBSERVABILITY_BOUNDARY_MODULES: tuple[Path, ...] = (
    RUNTIME_ROOT / "observability" / "context.py",
    RUNTIME_ROOT / "observability" / "ports.py",
)
OBSERVABILITY_BOUNDARY_FORBIDDEN_IMPORTS: frozenset[str] = frozenset(
    {
        "iris.adapters",
        "iris.features",
        "iris.presentation",
        "iris.safety",
        "iris.runtime.delivery",
        "iris.runtime.lifecycle",
        "iris.runtime.observability.diagnostics",
        "iris.runtime.observability.events",
        "iris.runtime.observability.llm",
        "iris.runtime.observability.logger",
        "iris.runtime.scheduler",
        "iris.runtime.state",
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


def test_runtime_service_does_not_directly_import_low_level_effects() -> None:
    """IrisRuntimeService は低レベル effect / feature / adapter を直接 import しない。"""
    service_path = RUNTIME_ROOT / "service.py"
    imports = _imports(service_path)
    violations = [
        imported
        for imported in imports
        for forbidden in RUNTIME_SERVICE_FORBIDDEN_DIRECT_IMPORTS
        if imported.startswith(forbidden)
    ]

    assert not violations, (
        "runtime.service must stay a thin boundary and avoid direct imports:\n"
        + "\n".join(violations)
    )


def test_runtime_observability_boundary_modules_do_not_import_concrete_implementations() -> None:
    """Observability boundary API modules は concrete implementation に依存しない。"""
    violations = [
        f"{path.relative_to(PROJECT_ROOT).as_posix()}: imports {imported}"
        for path in OBSERVABILITY_BOUNDARY_MODULES
        for imported in _imports(path)
        for forbidden in OBSERVABILITY_BOUNDARY_FORBIDDEN_IMPORTS
        if imported.startswith(forbidden)
    ]

    assert not violations, "runtime observability boundary modules must stay pure:\n" + "\n".join(
        violations
    )


def test_event_reaction_handler_remains_thin_bridge() -> None:
    """EventReaction handler must not grow feature policy or templates."""
    tree = ast.parse(EVENT_REACTION_RUNNER.read_text(encoding="utf-8"))
    imports = _imports(EVENT_REACTION_RUNNER)
    imported_violations = [
        imported
        for imported in imports
        for forbidden in RUNNER_FORBIDDEN_IMPORTS
        if imported.startswith(forbidden)
    ]
    name_violations = [
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id in RUNNER_FORBIDDEN_NAMES
    ]
    activity_kind_attributes = [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "activity_kind"
    ]
    text_violations = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and any(forbidden in node.value for forbidden in RUNNER_FORBIDDEN_TEXT)
    ]

    violations = [
        *(f"forbidden import {imported}" for imported in imported_violations),
        *(f"forbidden name {name}" for name in name_violations),
        *(f"forbidden activity branch attribute {attr}" for attr in activity_kind_attributes),
        *(f"forbidden reaction text {text!r}" for text in text_violations),
    ]

    assert not violations, "EventReaction handler must stay a thin bridge:\n" + "\n".join(
        violations,
    )
