"""Architecture guard: production code must not branch on test runtime state."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXCLUDED_ROOTS: frozenset[str] = frozenset({"iris/generated"})
EXCLUDED_FILE_SUFFIXES: tuple[str, ...] = (
    "/fake.py",
    "/fake_gateway.py",
    "/fake_resolvers.py",
)


@dataclass(frozen=True)
class _TestEnvironmentFinding:
    path: str
    line: int
    reason: str


def _relative_path(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _is_excluded(path: Path) -> bool:
    rel_path = _relative_path(path)
    if any(
        rel_path == excluded or rel_path.startswith(f"{excluded}/") for excluded in EXCLUDED_ROOTS
    ):
        return True
    return rel_path.startswith("iris/adapters/") and rel_path.endswith(EXCLUDED_FILE_SUFFIXES)


def _production_files() -> tuple[Path, ...]:
    return tuple(
        sorted(path for path in (PROJECT_ROOT / "iris").rglob("*.py") if not _is_excluded(path))
    )


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        if base is None:
            return node.attr
        return f"{base}.{node.attr}"
    return None


def _is_test_import(node: ast.Import | ast.ImportFrom) -> str | None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name == "pytest" or alias.name.startswith("tests"):
                return f"imports {alias.name}"
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if module in {"pytest", "tests"} or module.startswith("tests."):
            return f"imports {module}"
    return None


def _is_pytest_env_lookup(node: ast.Call) -> bool:
    name = _call_name(node.func)
    if name not in {"os.getenv", "os.environ.get"}:
        return False
    return bool(
        node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "PYTEST_CURRENT_TEST"
    )


def _collect_findings(path: Path) -> tuple[_TestEnvironmentFinding, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rel_path = _relative_path(path)
    findings: list[_TestEnvironmentFinding] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            import_reason = _is_test_import(node)
            if import_reason is not None:
                findings.append(_TestEnvironmentFinding(rel_path, node.lineno, import_reason))
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value == "PYTEST_CURRENT_TEST"
        ):
            findings.append(
                _TestEnvironmentFinding(
                    rel_path,
                    node.lineno,
                    "references PYTEST_CURRENT_TEST",
                )
            )
        if isinstance(node, ast.Call) and _is_pytest_env_lookup(node):
            findings.append(
                _TestEnvironmentFinding(
                    rel_path,
                    node.lineno,
                    "reads PYTEST_CURRENT_TEST",
                )
            )
    return tuple(findings)


def test_production_code_does_not_branch_on_test_environment() -> None:
    """Production code must not inspect pytest environment markers."""
    violations: list[str] = []
    for path in _production_files():
        violations.extend(
            f"{finding.path}:{finding.line}: {finding.reason}"
            for finding in _collect_findings(path)
            if "PYTEST_CURRENT_TEST" in finding.reason
        )

    assert not violations, "".join(
        (
            "Production code must not branch on pytest/test environment markers. ",
            "Use constructor injection, runtime wiring, or test fakes instead:\n",
            "\n".join(violations),
        )
    )


def test_production_code_does_not_import_tests_or_pytest() -> None:
    """Production code must not import pytest or tests."""
    violations: list[str] = []
    for path in _production_files():
        violations.extend(
            f"{finding.path}:{finding.line}: {finding.reason}"
            for finding in _collect_findings(path)
            if "imports" in finding.reason
        )

    assert not violations, "".join(
        (
            "Production code must not import pytest or tests. ",
            "Use constructor injection, runtime wiring, or test fakes instead:\n",
            "\n".join(violations),
        )
    )
