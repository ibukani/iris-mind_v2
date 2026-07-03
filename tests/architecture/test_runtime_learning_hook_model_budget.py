"""Runtime learning hook の model call budget architecture guard。"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_LEARNING_ROOT = PROJECT_ROOT / "iris" / "runtime" / "learning"
ADR_PATH = PROJECT_ROOT / "docs" / "adr" / "0015-local-model-call-budget-and-cascade-policy.md"

_FORBIDDEN_IMPORTS = (
    "iris.adapters.llm",
    "iris.runtime.wiring.llm",
    "iris.features.chat.definition",
)
_FORBIDDEN_GENERATION_METHODS = frozenset({"generate", "generate_response"})


def test_runtime_learning_hook_does_not_import_llm_generation_boundaries() -> None:
    """Runtime learning modules は LLM adapter / response generator に直接依存しない。"""
    offenders: list[str] = []
    for path in _runtime_learning_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                _collect_import_offenders(offenders, path, (alias.name for alias in node.names))
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                _collect_import_offenders(offenders, path, (node.module,))

    assert not offenders, "\n".join(sorted(offenders))


def test_runtime_learning_hook_does_not_call_generation_methods_directly() -> None:
    """Runtime learning hook は enqueue-only とし、重い生成呼び出しを直接実行しない。"""
    offenders: list[str] = []
    for path in _runtime_learning_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _FORBIDDEN_GENERATION_METHODS
        )

    assert not offenders, "\n".join(sorted(offenders))


def test_model_call_budget_adr_documents_downstream_issue_anchors() -> None:
    """Issue #88 の後続前提 issue を docs から参照できる。"""
    text = ADR_PATH.read_text(encoding="utf-8")

    for issue_number in ("#69", "#70", "#71", "#72", "#78"):
        assert issue_number in text


def test_model_call_budget_adr_documents_current_enforcement_boundary() -> None:
    """現段階の enforcement 範囲を docs で明示する。"""
    text = ADR_PATH.read_text(encoding="utf-8")

    assert "user-facing large LLM hot path" in text
    assert "config / policy contract" in text
    assert "実呼び出し箇所への enforcement はこの ADR の実装範囲外" in text
    assert "classifier / embedding / reranker" in text
    assert "後続 #69 / #70 / #71 / #72 / #78" in text


def test_model_call_budget_adr_documents_runtime_learning_enqueue_only() -> None:
    """Issue #88 の enqueue-only 方針は docs で固定する。"""
    text = ADR_PATH.read_text(encoding="utf-8")

    assert "runtime_learning_hook" in text
    assert "enqueue-only" in text
    assert "direct LLM call" in text


def _runtime_learning_python_files() -> tuple[Path, ...]:
    return tuple(sorted(RUNTIME_LEARNING_ROOT.rglob("*.py")))


def _collect_import_offenders(
    offenders: list[str],
    path: Path,
    module_names: Iterable[str],
) -> None:
    offenders.extend(
        f"{path.relative_to(PROJECT_ROOT)} imports {module_name}"
        for module_name in module_names
        if module_name.startswith(_FORBIDDEN_IMPORTS)
    )
