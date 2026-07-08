"""Small static architecture boundary guards をまとめて検査する。"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

import pytest

from tests.architecture.helpers.ast_utils import name_of, parse_python_file
from tests.architecture.helpers.project_paths import PROJECT_ROOT

if TYPE_CHECKING:
    from pathlib import Path

PRE_COMMIT_PATH = PROJECT_ROOT / ".pre-commit-config.yaml"
EVENT_REACTION_PLANNER_PATH = PROJECT_ROOT / "iris" / "features" / "event_reaction" / "planner.py"
FEATURES_ROOT = PROJECT_ROOT / "iris" / "features"
FORBIDDEN_RUNTIME_SERVICE_CONSTRUCTOR_TYPE_SUFFIXES = (
    "Integrator",
    "Store",
    "Journal",
    "Resolver",
    "Planner",
    "Runner",
)


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return tuple(names)


def _feature_python_files() -> tuple[Path, ...]:
    if not FEATURES_ROOT.is_dir():
        return ()
    return tuple(sorted(FEATURES_ROOT.rglob("*.py")))


def _iris_runtime_service_init() -> ast.FunctionDef:
    tree = parse_python_file(PROJECT_ROOT / "iris/runtime/service.py")
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "IrisRuntimeService":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    return item
    pytest.fail("IrisRuntimeService.__init__ not found")


def _check_precommit_autofix_policy() -> list[str]:
    text = PRE_COMMIT_PATH.read_text(encoding="utf-8")
    if "args: [--fix]" in text or "--fix" in text:
        return [".pre-commit-config.yaml must not run broad --fix"]
    return []


def _check_event_reaction_planner_templates() -> list[str]:
    source = EVENT_REACTION_PLANNER_PATH.read_text(encoding="utf-8")
    literals = {
        "Welcome back.",
        "Welcome back. I am here if you want to talk.",
    }
    return [
        f"planner.py contains user-facing literal {literal!r}; move it to templates.py"
        for literal in literals
        if literal in source
    ]


def _check_features_do_not_return_presented_output() -> list[str]:
    violations: list[str] = []
    for path in _feature_python_files():
        rel_path = path.relative_to(PROJECT_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.returns is not None:
                returns_str = ast.unparse(node.returns)
                if "PresentedOutput" in returns_str:
                    violations.append(f"{rel_path}: function {node.name!r} returns PresentedOutput")
    return violations


def _check_safety_policy_imports() -> list[str]:
    violations: list[str] = []
    policy_imports = _imports(PROJECT_ROOT / "iris/safety/policy_engine.py")
    forbidden_policy_imports = ("iris.adapters", "iris.runtime", "openai", "anthropic")
    violations.extend(
        f"iris/safety/policy_engine.py imports {name}"
        for name in policy_imports
        if name.startswith(forbidden_policy_imports)
    )

    proactive_feature = PROJECT_ROOT / "iris/features/proactive_talk"
    proactive_imports = tuple(
        name for path in proactive_feature.glob("*.py") for name in _imports(path)
    )
    violations.extend(
        f"iris/features/proactive_talk imports {name}"
        for name in proactive_imports
        if name.startswith(("iris.runtime", "iris.safety"))
    )
    return violations


def _check_runtime_service_constructor_shape() -> list[str]:
    violations: list[str] = []
    init_method = _iris_runtime_service_init()
    for arg in init_method.args.args[1:] + init_method.args.kwonlyargs:
        if arg.annotation is None:
            continue
        names = {name for node in ast.walk(arg.annotation) if (name := name_of(node)) is not None}
        if any(
            name.endswith(FORBIDDEN_RUNTIME_SERVICE_CONSTRUCTOR_TYPE_SUFFIXES)
            for name in names
            if name != "Sequence"
        ):
            violations.append(f"{arg.arg}: {ast.unparse(arg.annotation)}")
    return violations


def test_static_boundary_micro_guards() -> None:
    """Small boundary rules stay enforced without one-file-per-rule overhead."""
    violation_groups = {
        "pre-commit autofix policy": _check_precommit_autofix_policy(),
        "event reaction planner templates": _check_event_reaction_planner_templates(),
        "feature presentation boundary": _check_features_do_not_return_presented_output(),
        "safety policy imports": _check_safety_policy_imports(),
        "runtime service constructor shape": _check_runtime_service_constructor_shape(),
    }
    failures = [
        f"{group}:\n" + "\n".join(violations)
        for group, violations in violation_groups.items()
        if violations
    ]
    assert not failures, "\n\n".join(failures)
