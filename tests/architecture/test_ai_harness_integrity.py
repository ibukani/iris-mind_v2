"""Architecture guard for AI harness file and command integrity."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
from typing import TypeGuard

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

REQUIRED_AGENT_PATHS: frozenset[Path] = frozenset(
    {
        Path("AGENTS.md"),
        Path("CLAUDE.md"),
        Path(".agents/README.md"),
        Path(".agents/rules/architecture.md"),
        Path(".agents/rules/boundaries.md"),
        Path(".agents/rules/cognitive-cycle.md"),
        Path(".agents/rules/anti-patterns.md"),
        Path(".agents/rules/typing.md"),
        Path(".agents/rules/testing.md"),
        Path(".agents/rules/ai-harness.md"),
        Path(".agents/rules/instruction-design.md"),
        Path(".agents/rules/verification.md"),
        Path(".agents/workflows/add-feature.md"),
        Path(".agents/workflows/implement.md"),
        Path(".agents/workflows/bugfix.md"),
        Path(".agents/workflows/refactor.md"),
        Path(".agents/workflows/review.md"),
        Path(".agents/workflows/docs-update.md"),
        Path(".agents/workflows/test-fix.md"),
        Path(".agents/workflows/architecture.md"),
        Path(".agents/workflows/ai-harness.md"),
    }
)

EXPECTED_VERIFY_CHECKS: frozenset[str] = frozenset(
    {
        "lint",
        "format",
        "type",
        "pyright",
        "debt-registry",
        "architecture",
        "tests+coverage",
        "e2e",
    }
)

OPENCODE_COMMAND_TARGETS: dict[str, str] = {
    "ai-check": "make ai-check",
    "ai-quick": "make ai-quick",
    "ai-arch": "make ai-arch",
    "ai-report": "make ai-report",
}


def _target_names_from_makefile() -> set[str]:
    """Return Makefile target names."""
    target_pattern = re.compile(r"^([A-Za-z0-9_.-]+):")
    targets: set[str] = set()
    for line in (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8").splitlines():
        match = target_pattern.match(line)
        if match is not None:
            targets.add(match.group(1))
    return targets


def _verify_check_names() -> set[str]:
    """Return check names declared in scripts/verify.py."""
    verify_path = PROJECT_ROOT / "scripts" / "verify.py"
    tree = ast.parse(verify_path.read_text(encoding="utf-8"), filename=str(verify_path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "Check":
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            names.add(first_arg.value)
    return names


def _as_dict(value: object) -> dict[str, object]:
    """Return a string-keyed dict copy for parsed JSON objects."""
    if not _is_dict(value):
        return {}
    return {str(key): item for key, item in value.items()}


def _is_dict(value: object) -> TypeGuard[dict[object, object]]:
    """Narrow object to dict[object, object] for item iteration.

    Runtime check uses isinstance(dict) which erases type parameters, so the
    narrowed type uses the widest compatible parameter types.

    Returns:
        True if value is a dict, narrowing to the widened type.
    """
    return isinstance(value, dict)


def _is_list(value: object) -> TypeGuard[list[object]]:
    """Narrow object to list[object] for item iteration.

    Returns:
        True if value is a list, narrowing to the widened type.
    """
    return isinstance(value, list)


def test_required_ai_harness_paths_exist() -> None:
    """All mandatory AI harness paths referenced by entrypoint docs must exist."""
    missing = [
        str(path) for path in sorted(REQUIRED_AGENT_PATHS) if not (PROJECT_ROOT / path).exists()
    ]
    assert not missing, "missing AI harness paths:\n" + "\n".join(missing)


def test_opencode_instructions_reference_existing_files() -> None:
    """OpenCode instruction paths must stay valid."""
    config = _as_dict(json.loads((PROJECT_ROOT / "opencode.json").read_text(encoding="utf-8")))
    instructions_raw: object = config.get("instructions", ())
    if not _is_list(instructions_raw):
        instructions_raw = []
    instructions = list(instructions_raw)
    missing = [str(path) for path in instructions if not (PROJECT_ROOT / str(path)).is_file()]
    assert not missing, "opencode instructions reference missing files:\n" + "\n".join(missing)


def test_opencode_commands_match_make_targets() -> None:
    """OpenCode commands must call existing Makefile AI harness targets."""
    config = _as_dict(json.loads((PROJECT_ROOT / "opencode.json").read_text(encoding="utf-8")))
    commands_raw: object = config.get("command", ())
    if not _is_dict(commands_raw):
        commands_raw = {}
    commands = _as_dict(commands_raw)
    make_targets = _target_names_from_makefile()
    violations: list[str] = []

    for command_name, expected_template_text in OPENCODE_COMMAND_TARGETS.items():
        command_config: object = commands.get(command_name)
        if not _is_dict(command_config):
            violations.append(f"missing command {command_name}")
            continue
        command_dict = _as_dict(command_config)
        template: object = command_dict.get("template", "")
        if not isinstance(template, str) or expected_template_text not in template:
            violations.append(f"{command_name}: template must mention {expected_template_text}")
        make_target = command_name
        if make_target not in make_targets:
            violations.append(f"{command_name}: missing Makefile target {make_target}")

    assert not violations, "opencode command integrity violations:\n" + "\n".join(violations)


def test_ci_uses_explicit_supported_quality_gates() -> None:
    """CI must run the supported split quality gates explicitly."""
    makefile_text = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
    ci_text = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "check:" in makefile_text
    assert "uv run python scripts/verify.py" in makefile_text
    assert "verify: check" in makefile_text

    required_ci_commands = (
        "make quick",
        "make coverage",
        "make e2e",
        "make generate-protos",
        "git diff --exit-code iris/generated",
        "make runtime-doctor-json",
        "uv build",
    )

    missing = [command for command in required_ci_commands if command not in ci_text]
    assert not missing, "CI is missing required quality gates:\n" + "\n".join(missing)


def test_verify_script_contains_all_required_checks() -> None:
    """scripts/verify.py must keep every strict AI harness check in the gate."""
    check_names = _verify_check_names()
    missing = EXPECTED_VERIFY_CHECKS - check_names
    assert not missing, f"scripts/verify.py missing checks: {sorted(missing)}"
