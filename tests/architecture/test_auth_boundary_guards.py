"""Runtime auth boundary architecture guards."""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def test_cognitive_and_contracts_do_not_import_runtime_auth() -> None:
    """cognitive/contracts は runtime.auth に依存しない。"""
    for package in ("iris/cognitive", "iris/contracts"):
        for path in (_ROOT / package).rglob("*.py"):
            imports = _imports(path)
            assert "iris.runtime.auth" not in imports


def test_runtime_service_does_not_import_auth_verifier() -> None:
    """IrisRuntimeService は concrete verifier を import しない。"""
    imports = _imports(_ROOT / "iris/runtime/service.py")
    assert "iris.runtime.auth.static_tokens" not in imports


def test_auth_core_does_not_import_protobuf_or_provider_sdks() -> None:
    """Auth core は protobuf DTO/provider SDK に依存しない。"""
    for path in (_ROOT / "iris/runtime/auth").rglob("*.py"):
        imports = _imports(path)
        assert not any(item.startswith("iris.generated") for item in imports)
        assert "httpx" not in imports
        assert "openai" not in imports


def test_auth_policy_does_not_construct_outputs_or_actions() -> None:
    """Auth policy は PresentedOutput/AppAction を構築しない。"""
    tree = ast.parse((_ROOT / "iris/runtime/auth/policy.py").read_text())
    constructed = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "PresentedOutput" not in constructed
    assert "AppAction" not in constructed


def _imports(path: Path) -> frozenset[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            values.add(node.module)
    return frozenset(values)
