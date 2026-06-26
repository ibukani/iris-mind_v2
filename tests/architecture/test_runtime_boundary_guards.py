"""Executable guards for runtime boundary policy."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from tests.architecture.helpers.ast_utils import imported_modules, name_of, parse_python_file
from tests.architecture.helpers.project_paths import PROJECT_ROOT

if TYPE_CHECKING:
    from pathlib import Path

RUNTIME_SERVICE = PROJECT_ROOT / "iris/runtime/service.py"
OBSERVATION_ROUTER = PROJECT_ROOT / "iris/runtime/observation_router.py"
SCHEDULER_RUNNER = PROJECT_ROOT / "iris/runtime/scheduler/runner.py"
DELIVERY_ROOT = PROJECT_ROOT / "iris/runtime/delivery"
SCHEDULER_ROOT = PROJECT_ROOT / "iris/runtime/scheduler"
GRPC_SERVER = PROJECT_ROOT / "iris/adapters/grpc/server.py"

EXTERNAL_SDK_IMPORT_PREFIXES = (
    "discord",
    "openai",
    "ollama",
    "slack_sdk",
    "twitchio",
)


def test_runtime_service_does_not_import_side_effect_boundaries() -> None:
    """IrisRuntimeService stays thin and transport-independent."""
    forbidden_prefixes = (
        "iris.runtime.scheduler",
        "iris.runtime.delivery",
        "iris.adapters",
        "iris.presentation",
        "iris.safety",
        *EXTERNAL_SDK_IMPORT_PREFIXES,
    )
    imports = imported_modules(parse_python_file(RUNTIME_SERVICE))

    violations = sorted(imported for imported in imports if imported.startswith(forbidden_prefixes))

    assert not violations


def test_concrete_observation_runtime_routing_lives_only_in_router() -> None:
    """Concrete Observation isinstance/type/match routing is centralized."""
    concrete_observations = _concrete_observation_names()
    violations: list[str] = []
    for path in _runtime_python_files():
        if path == OBSERVATION_ROUTER:
            continue
        violations.extend(_concrete_observation_branch_violations(path, concrete_observations))

    assert not violations, "\n".join(violations)


def test_runtime_service_constructs_only_no_send_presented_output() -> None:
    """Runtime service may create PresentedOutput(text=None), not user-facing text."""
    tree = parse_python_file(RUNTIME_SERVICE)
    violations: list[str] = []
    app_action_names = _app_action_subclass_names()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if name_of(node.func) == "PresentedOutput":
            # Detect keyword text=<non-None>
            violations.extend(
                f"PresentedOutput text at line {node.lineno}"
                for keyword in node.keywords
                if keyword.arg == "text" and not _is_none_constant(keyword.value)
            )
            # Detect positional first arg that is not None
            if node.args and not _is_none_constant(node.args[0]):
                violations.append(f"PresentedOutput positional text at line {node.lineno}")
        if name_of(node.func) in app_action_names:
            violations.append(f"AppAction construction at line {node.lineno}")

    assert not violations, "\n".join(violations)


def test_scheduler_runner_does_not_import_generation_or_transport_adapters() -> None:
    """Scheduler emits observations and enqueues after delivery safety only."""
    forbidden_prefixes = (
        "iris.adapters.llm",
        "iris.presentation",
        "iris.adapters.grpc.server",
        *EXTERNAL_SDK_IMPORT_PREFIXES,
    )
    imports = imported_modules(parse_python_file(SCHEDULER_RUNNER))
    violations = sorted(imported for imported in imports if imported.startswith(forbidden_prefixes))

    assert not violations


def test_scheduler_modules_do_not_import_generation_or_transport_adapters() -> None:
    """All scheduler modules are isolated from LLM, presentation, gRPC server, and external SDKs."""
    forbidden_prefixes = (
        "iris.adapters.llm",
        "iris.presentation",
        "iris.adapters.grpc.server",
        *EXTERNAL_SDK_IMPORT_PREFIXES,
    )
    violations: list[str] = []
    for path in sorted(SCHEDULER_ROOT.rglob("*.py")):
        imports = imported_modules(parse_python_file(path))
        violations.extend(
            f"{path.relative_to(PROJECT_ROOT)} imports {imported}"
            for imported in imports
            if imported.startswith(forbidden_prefixes)
        )

    assert not violations, "\n".join(violations)


def test_delivery_outbox_does_not_import_runtime_or_sender_boundaries() -> None:
    """DeliveryOutbox remains pull-based storage, not sender/runtime owner."""
    forbidden_prefixes = (
        "iris.runtime.service",
        "iris.runtime.app",
        "iris.cognitive",
        "iris.presentation",
        *EXTERNAL_SDK_IMPORT_PREFIXES,
    )
    violations: list[str] = []
    for path in sorted(DELIVERY_ROOT.rglob("*.py")):
        imports = imported_modules(parse_python_file(path))
        violations.extend(
            f"{path.relative_to(PROJECT_ROOT)} imports {imported}"
            for imported in imports
            if imported.startswith(forbidden_prefixes)
        )

    assert not violations, "\n".join(violations)


def test_grpc_server_does_not_depend_on_concrete_delivery_or_scheduler() -> None:
    """GRPC server depends on runtime service and AppActionBroker protocol only."""
    forbidden_prefixes = (
        "iris.runtime.delivery",
        "iris.runtime.scheduler",
    )
    imports = imported_modules(parse_python_file(GRPC_SERVER))
    violations = sorted(imported for imported in imports if imported.startswith(forbidden_prefixes))

    assert not violations


def _runtime_python_files() -> tuple[Path, ...]:
    return tuple(sorted((PROJECT_ROOT / "iris/runtime").rglob("*.py")))


def _concrete_observation_names() -> set[str]:
    tree = parse_python_file(PROJECT_ROOT / "iris/contracts/observations.py")
    concrete: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name == "Observation":
            continue
        base_names = {name_of(base) for base in node.bases}
        if "Observation" in base_names:
            concrete.add(node.name)
    return concrete


def _concrete_observation_branch_violations(
    path: Path,
    concrete_observations: set[str],
) -> list[str]:
    tree = parse_python_file(path)
    violations: list[str] = []
    rel = path.relative_to(PROJECT_ROOT)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and name_of(node.func) == "isinstance"
            and len(node.args) >= 2
            and _contains_observation_name(node.args[1], concrete_observations)
        ):
            violations.append(f"{rel}:{node.lineno} isinstance concrete Observation")
        if isinstance(node, ast.Compare) and _is_type_observation_compare(
            node, concrete_observations
        ):
            violations.append(f"{rel}:{node.lineno} type concrete Observation")
        if isinstance(node, ast.Match):
            violations.extend(
                f"{rel}:{node.lineno} match concrete Observation"
                for case in node.cases
                if _contains_observation_name(case.pattern, concrete_observations)
            )
    return violations


def _contains_observation_name(node: ast.AST, concrete_observations: set[str]) -> bool:
    if name_of(node) in concrete_observations:
        return True
    return any(name_of(child) in concrete_observations for child in ast.walk(node))


def _is_none_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _is_type_observation_compare(
    node: ast.Compare,
    concrete_observations: set[str],
) -> bool:
    operands = (node.left, *node.comparators)
    has_type_call = any(
        isinstance(operand, ast.Call) and name_of(operand.func) == "type" for operand in operands
    )
    return has_type_call and any(
        _contains_observation_name(operand, concrete_observations) for operand in operands
    )


def _app_action_subclass_names() -> set[str]:
    tree = parse_python_file(PROJECT_ROOT / "iris/contracts/actions.py")
    subclasses: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name == "AppAction":
            continue
        base_names = {name_of(base) for base in node.bases}
        if "AppAction" in base_names:
            subclasses.add(node.name)
    return subclasses
