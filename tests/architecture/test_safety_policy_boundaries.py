"""Safety policy architecture boundary guards。"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).parents[2]


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return tuple(names)


def test_policy_engine_has_no_llm_adapter_or_runtime_dependency() -> None:
    """Deterministic policy engine は external/LLM/runtime 層に依存しない。"""
    imports = _imports(_ROOT / "iris/safety/policy_engine.py")
    forbidden = ("iris.adapters", "iris.runtime", "openai", "anthropic")
    assert not any(name.startswith(forbidden) for name in imports)


def test_proactive_feature_does_not_import_runtime_or_safety_engine() -> None:
    """Proactive feature は runtime/delivery/concrete safety に依存しない。"""
    feature = _ROOT / "iris/features/proactive_talk"
    imports = tuple(name for path in feature.glob("*.py") for name in _imports(path))
    forbidden = ("iris.runtime", "iris.safety")
    assert not any(name.startswith(forbidden) for name in imports)
