"""Architecture guard: production code must not gain test-double shortcuts."""

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
TEST_DOUBLE_TOKENS: tuple[str, ...] = (
    "Fake",
    "Dummy",
    "Mock",
    "Stub",
    "Placeholder",
)


@dataclass(frozen=True)
class _TestDoubleFinding:
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


def _has_test_double_token(name: str) -> bool:
    return any(token in name for token in TEST_DOUBLE_TOKENS)


def _test_import_reason(node: ast.Import | ast.ImportFrom) -> str | None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name in {"pytest", "unittest.mock"} or alias.name.startswith("tests."):
                return f"imports {alias.name}"
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if module in {"pytest", "unittest.mock", "tests"} or module.startswith("tests."):
            return f"imports {module}"
    return None


def _collect_findings(path: Path) -> tuple[_TestDoubleFinding, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rel_path = _relative_path(path)
    findings: list[_TestDoubleFinding] = []
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ) and _has_test_double_token(node.name):
            findings.append(
                _TestDoubleFinding(
                    rel_path,
                    node.lineno,
                    f"test-double name {node.name}",
                )
            )
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            import_reason = _test_import_reason(node)
            if import_reason is not None:
                findings.append(_TestDoubleFinding(rel_path, node.lineno, import_reason))
    return tuple(findings)


def test_test_double_names_do_not_appear_in_production_code() -> None:
    """Test doubles belong in tests or explicit fake adapter modules."""
    violations: list[str] = []
    for path in _production_files():
        violations.extend(
            f"{finding.path}:{finding.line}: {finding.reason}"
            for finding in _collect_findings(path)
        )

    assert not violations, "".join(
        (
            "Do not add fake/dummy/mock/stub production shortcuts. ",
            "Keep test doubles in tests or explicit fake adapter modules:\n",
            "\n".join(violations),
        )
    )
