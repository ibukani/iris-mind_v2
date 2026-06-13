"""RuntimeService constructor が低レベル effect を直接受けないことを検査する。"""

from __future__ import annotations

import ast

import pytest

from tests.architecture.helpers.ast_utils import name_of, parse_python_file
from tests.architecture.helpers.project_paths import PROJECT_ROOT

FORBIDDEN_CONSTRUCTOR_TYPE_SUFFIXES = (
    "Integrator",
    "Store",
    "Journal",
    "Resolver",
    "Planner",
    "Runner",
)


def _iris_runtime_service_init() -> ast.FunctionDef:
    tree = parse_python_file(PROJECT_ROOT / "iris/runtime/service.py")
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "IrisRuntimeService":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    return item
    pytest.fail("IrisRuntimeService.__init__ not found")


def test_runtime_service_init_does_not_accept_low_level_effect_objects() -> None:
    """RuntimeService は boundary abstraction だけを constructor で受ける。"""
    init_method = _iris_runtime_service_init()
    violations: list[str] = []
    for arg in init_method.args.args[1:] + init_method.args.kwonlyargs:
        if arg.annotation is None:
            continue
        names = {name for node in ast.walk(arg.annotation) if (name := name_of(node)) is not None}
        if any(
            name.endswith(FORBIDDEN_CONSTRUCTOR_TYPE_SUFFIXES)
            for name in names
            if name != "Sequence"
        ):
            violations.append(f"{arg.arg}: {ast.unparse(arg.annotation)}")
    assert not violations, "\n".join(violations)
