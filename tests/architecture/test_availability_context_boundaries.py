"""Availability / context assembly 追加に伴う architecture boundary tests."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _get_imports(tree: ast.Module) -> list[str]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _assert_no_forbidden_imports(
    path: Path,
    forbidden_prefixes: tuple[str, ...],
) -> None:
    """指定ファイルが禁止prefixのimportを含まないことを検証する。"""
    assert path.is_file(), f"Target file must exist: {path}"

    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = _get_imports(tree)
    violations = [imp for imp in imports for prefix in forbidden_prefixes if imp.startswith(prefix)]
    assert not violations, (
        f"{path.relative_to(PROJECT_ROOT)} must not import {forbidden_prefixes}: {violations}"
    )


def test_availability_resolver_does_not_import_cognitive() -> None:
    """AvailabilityResolver は cognitive 層に依存してはならない。"""
    path = PROJECT_ROOT / "iris" / "runtime" / "state" / "availability.py"
    _assert_no_forbidden_imports(path, ("iris.cognitive", "iris.adapters"))


def test_cognitive_frame_does_not_import_runtime() -> None:
    """WorkspaceFrame / SituationContextSnapshot は runtime 層に依存してはならない。"""
    path = PROJECT_ROOT / "iris" / "cognitive" / "workspace" / "frame.py"
    _assert_no_forbidden_imports(path, ("iris.runtime",))


def test_workspace_context_assembler_uses_shared_context_contract() -> None:
    """WorkspaceContextAssembler は共有contract snapshotを組み立てる。"""
    path = PROJECT_ROOT / "iris" / "runtime" / "state" / "context_assembler.py"
    assert path.is_file(), "context_assembler.py must exist"

    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = _get_imports(tree)
    assert "iris.contracts.workspace_context" in imports
    assert "iris.cognitive.workspace.frame" not in imports


def test_workspace_context_assembler_does_not_import_adapters() -> None:
    """WorkspaceContextAssembler は adapter 実装に依存してはならない。"""
    path = PROJECT_ROOT / "iris" / "runtime" / "state" / "context_assembler.py"
    _assert_no_forbidden_imports(path, ("iris.adapters", "iris.runtime.adapters"))


def test_event_reaction_feature_does_not_import_runtime_or_adapters() -> None:
    """EventReaction feature は runtime / adapters / app_gateway に依存してはならない。"""
    path = PROJECT_ROOT / "iris" / "features" / "event_reaction" / "planner.py"
    _assert_no_forbidden_imports(
        path,
        ("iris.adapters", "iris.runtime", "iris.runtime.app_gateway"),
    )


def test_event_reaction_handler_does_not_import_adapters_or_app_gateway() -> None:
    """EventReaction handler は adapters / app_gateway に依存してはならない。"""
    path = PROJECT_ROOT / "iris" / "runtime" / "ingress" / "activity_event_reaction.py"
    _assert_no_forbidden_imports(
        path,
        ("iris.adapters", "iris.runtime.adapters", "iris.runtime.app_gateway"),
    )


def test_event_reaction_contracts_do_not_import_runtime_or_adapters() -> None:
    """EventReaction 契約層は runtime / adapters に依存してはならない。"""
    path = PROJECT_ROOT / "iris" / "contracts" / "event_reaction.py"
    _assert_no_forbidden_imports(path, ("iris.runtime", "iris.adapters"))
