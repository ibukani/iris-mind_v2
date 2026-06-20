"""Proactive scheduler / delivery architecture boundary guards."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _python_files(relative_dir: str) -> tuple[Path, ...]:
    """Return Python files under a project-relative directory."""
    return tuple(sorted((PROJECT_ROOT / relative_dir).rglob("*.py")))


def _imports(path: Path) -> set[str]:
    """Collect imported module names from a Python file.

    Returns:
        取得した module 名の集合。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return imports


def _source(path: Path) -> str:
    """Read source text.

    Returns:
        ファイルのソーステキスト。
    """
    return path.read_text(encoding="utf-8")


def test_scheduler_does_not_import_llm_or_external_clients() -> None:
    """Scheduler must not call LLM or provider SDKs directly."""
    forbidden = ("iris.adapters.llm", "discord", "voice", "cli")
    violations = [
        f"{path.relative_to(PROJECT_ROOT)} imports {module}"
        for path in _python_files("iris/runtime/scheduler")
        for module in _imports(path)
        if module.startswith(forbidden)
    ]
    assert not violations


def test_features_proactive_talk_does_not_import_runtime_delivery_scheduler_or_safety() -> None:
    """proactive_talk feature must not import runtime delivery/scheduler/safety."""
    forbidden = ("iris.runtime.delivery", "iris.runtime.scheduler", "iris.safety")
    violations = [
        f"{path.relative_to(PROJECT_ROOT)} imports {module}"
        for path in _python_files("iris/features/proactive_talk")
        for module in _imports(path)
        if module.startswith(forbidden)
    ]
    assert not violations


def test_cognitive_does_not_import_runtime_delivery_scheduler() -> None:
    """Cognitive layer must not depend on runtime scheduler or delivery."""
    forbidden = ("iris.runtime.delivery", "iris.runtime.scheduler", "iris.contracts.delivery")
    violations = [
        f"{path.relative_to(PROJECT_ROOT)} imports {module}"
        for path in _python_files("iris/cognitive")
        for module in _imports(path)
        if module.startswith(forbidden)
    ]
    assert not violations


def test_safety_does_not_import_runtime_or_cognitive() -> None:
    """Safety gates must not depend on runtime or cognitive implementations."""
    forbidden = ("iris.runtime", "iris.cognitive")
    violations = [
        f"{path.relative_to(PROJECT_ROOT)} imports {module}"
        for path in _python_files("iris/safety")
        for module in _imports(path)
        if module.startswith(forbidden)
    ]
    assert not violations


def test_grpc_adapter_does_not_import_concrete_runtime_delivery() -> None:
    """GRPC adapter may use delivery contracts and broker protocol, not concrete outbox."""
    forbidden = ("iris.runtime.delivery.in_memory", "iris.runtime.delivery.broker")
    violations = [
        f"{path.relative_to(PROJECT_ROOT)} imports {module}"
        for path in _python_files("iris/adapters/grpc")
        for module in _imports(path)
        if module.startswith(forbidden)
    ]
    assert not violations


def test_delivery_outbox_does_not_import_runtime_app_or_cognitive_cycle() -> None:
    """Delivery outbox must not execute app/cognitive behavior."""
    forbidden = ("iris.runtime.app", "iris.cognitive")
    violations = [
        f"{path.relative_to(PROJECT_ROOT)} imports {module}"
        for path in _python_files("iris/runtime/delivery")
        for module in _imports(path)
        if module.startswith(forbidden)
    ]
    assert not violations


def test_iris_runtime_service_does_not_import_scheduler_or_delivery() -> None:
    """IrisRuntimeService remains scheduler/delivery agnostic."""
    imports = _imports(PROJECT_ROOT / "iris/runtime/service.py")
    assert not {
        module
        for module in imports
        if module.startswith(("iris.runtime.scheduler", "iris.runtime.delivery"))
    }


def test_no_action_not_enqueued_in_delivery_outbox() -> None:
    """DeliveryOutbox implementation explicitly rejects NoAction."""
    text = _source(PROJECT_ROOT / "iris/runtime/delivery/in_memory.py")
    assert "NoAction" in text
    assert "no_action_not_deliverable" in text


def test_runtime_server_contains_no_delivery_transition_logic() -> None:
    """runtime/server.py must not own delivery state transitions."""
    text = _source(PROJECT_ROOT / "iris/runtime/server.py")
    forbidden = ("FAILED_RETRYABLE", "FAILED_PERMANENT", "lease_id", "idempotency_key")
    assert not {token for token in forbidden if token in text}
