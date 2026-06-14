"""Architecture guard: tests must not be disabled to pass weak gates."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class _DisabledTestOccurrence:
    path: str
    line: int
    kind: str


# Existing architecture guards use skips only for targets that may not exist in
# partial architecture phases. New entries must be exact and justified.
_APPROVED_TEST_DISABLING: frozenset[_DisabledTestOccurrence] = frozenset(
    {
        _DisabledTestOccurrence(
            "tests/architecture/test_availability_context_boundaries.py",
            29,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_availability_context_boundaries.py",
            55,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_availability_context_boundaries.py",
            90,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_boundaries.py",
            90,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_boundaries.py",
            107,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_anti_patterns.py",
            181,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_anti_patterns.py",
            205,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_anti_patterns.py",
            284,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_anti_patterns.py",
            310,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_anti_patterns.py",
            339,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_anti_patterns.py",
            366,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_anti_patterns.py",
            413,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_anti_patterns.py",
            448,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_anti_patterns.py",
            476,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_anti_patterns.py",
            500,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_config_env_ownership.py",
            88,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_contracts.py",
            33,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_contracts.py",
            248,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_contracts.py",
            328,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_contracts.py",
            413,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_contracts.py",
            441,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_contracts.py",
            480,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_contracts.py",
            494,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_contracts.py",
            518,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_contracts.py",
            554,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_cognitive_runtime_contracts.py",
            580,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_target_architecture_guards.py",
            164,
            "pytest.skip",
        ),
        _DisabledTestOccurrence(
            "tests/architecture/test_target_architecture_guards.py",
            354,
            "pytest.skip",
        ),
    }
)


def _python_test_files() -> tuple[Path, ...]:
    return tuple(sorted((PROJECT_ROOT / "tests").rglob("*.py")))


def _relative_path(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        if base is None:
            return node.attr
        return f"{base}.{node.attr}"
    return None


def _disabled_kind(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        name = _call_name(node.func)
        if name in {"pytest.skip", "pytest.xfail"}:
            return name
    name = _call_name(node)
    if name in {
        "pytest.mark.skip",
        "pytest.mark.skipif",
        "pytest.mark.xfail",
    }:
        return name
    return None


def _collect_disabled_tests(path: Path) -> tuple[_DisabledTestOccurrence, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rel_path = _relative_path(path)
    occurrences: list[_DisabledTestOccurrence] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            kind = _disabled_kind(node)
            if kind is not None:
                occurrences.append(_DisabledTestOccurrence(rel_path, node.lineno, kind))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for decorator in node.decorator_list:
                kind = _disabled_kind(decorator)
                if kind is not None:
                    occurrences.append(_DisabledTestOccurrence(rel_path, decorator.lineno, kind))
    return tuple(occurrences)


def test_tests_are_not_disabled_with_skip_or_xfail() -> None:
    """Tests must not be disabled instead of fixed."""
    violations: list[str] = []
    for path in _python_test_files():
        violations.extend(
            f"{occurrence.path}:{occurrence.line}: {occurrence.kind}"
            for occurrence in _collect_disabled_tests(path)
            if occurrence not in _APPROVED_TEST_DISABLING
        )

    assert not violations, "".join(
        (
            "Do not disable tests with skip/xfail to make gates pass. ",
            "Fix the test or implementation instead:\n",
            "\n".join(violations),
        )
    )
