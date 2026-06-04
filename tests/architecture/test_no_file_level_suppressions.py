"""Architecture guard against file-level quality suppression escape hatches."""

from __future__ import annotations

from pathlib import Path

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


def _python_files(roots: tuple[Path, ...]) -> tuple[Path, ...]:
    """Return Python files under roots."""
    files: list[Path] = []
    for root in roots:
        base = PROJECT_ROOT / root
        if base.is_dir():
            files.extend(base.rglob("*.py"))
    return tuple(sorted(files))


def _file_level_suppressions(path: Path) -> list[str]:
    """Return file-level suppression lines from a file's header."""
    findings: list[str] = []
    header_lines = path.read_text(encoding="utf-8").splitlines()[:10]
    for line_number, line in enumerate(header_lines, start=1):
        stripped = line.strip()
        if any(stripped.startswith(token) for token in FILE_LEVEL_SUPPRESSIONS):
            findings.append(f"{path}:{line_number}: {stripped}")
    return findings


def test_file_level_suppressions_are_forbidden_in_protected_layers() -> None:
    """Protected layers must not use file-level quality gate suppressions."""
    violations: list[str] = []
    for path in _python_files(PROTECTED_ROOTS):
        violations.extend(_file_level_suppressions(path))

    assert not violations, "file-level suppressions in protected layers:\n" + "\n".join(
        violations,
    )


def test_file_level_suppressions_require_explicit_allowlist_in_exception_zones() -> None:
    """Exception zones must not silently disable whole-file quality checks."""
    violations: list[str] = []
    for path in _python_files(EXCEPTION_ROOTS):
        violations.extend(_file_level_suppressions(path))

    assert not violations, "unapproved file-level suppressions in exception zones:\n" + "\n".join(
        violations,
    )
