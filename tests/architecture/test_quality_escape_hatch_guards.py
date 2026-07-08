"""Quality gate escape hatch をまとめて禁止する architecture guard。"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import re
from typing import override

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROTECTED_ROOTS: tuple[Path, ...] = (
    Path("iris/contracts"),
    Path("iris/core"),
    Path("iris/cognitive"),
    Path("iris/features"),
    Path("iris/presentation"),
    Path("iris/safety"),
    Path("iris/runtime"),
)
EXCEPTION_ROOTS: tuple[Path, ...] = (
    Path("iris/adapters"),
    Path("scripts"),
    Path("tests"),
)
FILE_LEVEL_SUPPRESSIONS: frozenset[str] = frozenset(
    {
        "# ruff: noqa",
        "# flake8: noqa",
        "# mypy: ignore-errors",
        "# type: ignore-errors",
        "# pyright: basic",
        "# pyright: strict=false",
        "# pyright: report",
    }
)
SUPPRESSION_TOKENS: tuple[str, ...] = (
    "# noqa",
    "# type: ignore",
    "# pyright: ignore",
)
NOQA_WITH_REASON_RE = re.compile(
    r"# noqa:\s*[A-Z]+[0-9]+(?:\s*,\s*[A-Z]+[0-9]+)*(?:\s+--|\s+#)\s+\S+",
)
TYPE_IGNORE_WITH_REASON_RE = re.compile(
    r"# type:\s*ignore\[[a-z0-9\-,]+\](?:\s+--|\s+#)\s+\S+",
)
PYRIGHT_IGNORE_WITH_REASON_RE = re.compile(
    r"# pyright:\s*ignore\[[A-Za-z0-9_,]+\](?:\s+--|\s+#)\s+\S+",
)
SUPPRESSION_CHECKS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("# noqa", NOQA_WITH_REASON_RE),
    ("# type: ignore", TYPE_IGNORE_WITH_REASON_RE),
    ("# pyright: ignore", PYRIGHT_IGNORE_WITH_REASON_RE),
)
SCANNER_FIXTURE_FILES: frozenset[Path] = frozenset(
    {
        Path("tests/architecture/test_quality_escape_hatch_guards.py"),
        Path("tests/architecture/test_suppression_debt_registry.py"),
        Path("tests/architecture/test_suppression_debt_registry_is_frozen.py"),
    },
)
ALLOWED_CAST_FILES: frozenset[Path] = frozenset()
ALLOWED_SUPPRESSION_LINES: frozenset[tuple[Path, int]] = frozenset()
ALLOWED_UNREASONED_SUPPRESSION_LINES: frozenset[tuple[Path, int]] = frozenset()


@dataclass(frozen=True)
class _DisabledTestOccurrence:
    path: str
    line: int
    kind: str


APPROVED_TEST_DISABLING: frozenset[_DisabledTestOccurrence] = frozenset(
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


def _python_files(roots: tuple[Path, ...]) -> tuple[Path, ...]:
    files: list[Path] = []
    for root in roots:
        base = PROJECT_ROOT / root
        if base.is_dir():
            files.extend(base.rglob("*.py"))
    return tuple(sorted(files))


def _protected_python_files() -> tuple[Path, ...]:
    return tuple(path for path in _python_files(PROTECTED_ROOTS) if path not in ALLOWED_CAST_FILES)


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


def _is_cast_call(node: ast.Call) -> bool:
    return _call_name(node.func) in {"cast", "typing.cast"}


def _collect_protected_casts() -> list[str]:
    violations: list[str] = []
    for path in _protected_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        violations.extend(
            f"{path}:{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and _is_cast_call(node)
        )
    return violations


def _file_level_suppressions(path: Path) -> list[str]:
    findings: list[str] = []
    header_lines = path.read_text(encoding="utf-8").splitlines()[:10]
    for line_number, line in enumerate(header_lines, start=1):
        stripped = line.strip()
        if any(stripped.startswith(token) for token in FILE_LEVEL_SUPPRESSIONS):
            findings.append(f"{path}:{line_number}: {stripped}")
    return findings


def _collect_file_level_suppressions() -> list[str]:
    violations: list[str] = []
    for path in _python_files((*PROTECTED_ROOTS, *EXCEPTION_ROOTS)):
        violations.extend(_file_level_suppressions(path))
    return violations


def _suppression_comment_violations(path: Path) -> list[str]:
    violations: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if (path, line_number) in ALLOWED_SUPPRESSION_LINES:
            continue
        if any(token in line for token in SUPPRESSION_TOKENS):
            violations.append(f"{path}:{line_number}: {line.strip()}")
    return violations


def _is_object_setattr_call(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "__setattr__"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "object"
    )


class _SetattrVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[str] = []

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name == "__post_init__":
            return
        self.generic_visit(node)

    @override
    def visit_Call(self, node: ast.Call) -> None:
        if _is_object_setattr_call(node):
            self.violations.append(f"{self.path}:{node.lineno}: object.__setattr__")
        self.generic_visit(node)


def _object_setattr_violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    visitor = _SetattrVisitor(path)
    visitor.visit(tree)
    return visitor.violations


def _collect_protected_suppressions() -> list[str]:
    violations: list[str] = []
    for path in _python_files(PROTECTED_ROOTS):
        violations.extend(_suppression_comment_violations(path))
        violations.extend(_object_setattr_violations(path))
    return violations


def _collect_unreasoned_exception_zone_suppressions() -> list[str]:
    violations: list[str] = []
    for path in _python_files(EXCEPTION_ROOTS):
        rel_path = Path(_relative_path(path))
        if rel_path in SCANNER_FIXTURE_FILES:
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if (path, line_number) in ALLOWED_UNREASONED_SUPPRESSION_LINES:
                continue
            for token, pattern in SUPPRESSION_CHECKS:
                if token in line and pattern.search(line) is None:
                    violations.append(f"{path}:{line_number}: {line.strip()}")
    return violations


def _disabled_kind(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        name = _call_name(node.func)
        if name in {"pytest.skip", "pytest.xfail"}:
            return name
    name = _call_name(node)
    if name in {"pytest.mark.skip", "pytest.mark.skipif", "pytest.mark.xfail"}:
        return name
    return None


def _collect_disabled_tests(path: Path) -> tuple[_DisabledTestOccurrence, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
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


def _collect_unapproved_test_disabling() -> list[str]:
    violations: list[str] = []
    for path in sorted((PROJECT_ROOT / "tests").rglob("*.py")):
        violations.extend(
            f"{occurrence.path}:{occurrence.line}: {occurrence.kind}"
            for occurrence in _collect_disabled_tests(path)
            if occurrence not in APPROVED_TEST_DISABLING
        )
    return violations


def test_quality_gate_escape_hatches_are_forbidden() -> None:
    """Quality gate escape hatches stay forbidden without one-file-per-rule overhead."""
    violation_groups = {
        "typing.cast in protected layers": _collect_protected_casts(),
        "file-level suppression": _collect_file_level_suppressions(),
        "local suppression or object.__setattr__ in protected layers": (
            _collect_protected_suppressions()
        ),
        "unreasoned suppression in exception zones": (
            _collect_unreasoned_exception_zone_suppressions()
        ),
        "skip/xfail test disabling": _collect_unapproved_test_disabling(),
    }
    failures = [
        f"{group}:\n" + "\n".join(violations)
        for group, violations in violation_groups.items()
        if violations
    ]
    assert not failures, "\n\n".join(failures)
