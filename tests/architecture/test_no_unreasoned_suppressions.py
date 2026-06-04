"""Architecture guard for documented suppression usage in exception zones."""

from __future__ import annotations

from pathlib import Path
import re

SUPPRESSION_ROOTS: tuple[Path, ...] = (
    Path("iris/adapters"),
    Path("scripts"),
    Path("tests"),
)

NOQA_WITH_REASON_RE = re.compile(
    r"# noqa:\s*[A-Z]+[0-9]+(?:\s*,\s*[A-Z]+[0-9]+)*\s+--\s+\S+",
)
TYPE_IGNORE_WITH_REASON_RE = re.compile(
    r"# type:\s*ignore\[[a-z0-9\-,]+\]\s+--\s+\S+",
)
PYRIGHT_IGNORE_WITH_REASON_RE = re.compile(
    r"# pyright:\s*ignore\[[A-Za-z0-9_,]+\]\s+--\s+\S+",
)

# Existing architecture scan exception. New suppressions must include a reason.
ALLOWED_UNREASONED_SUPPRESSION_LINES: frozenset[tuple[Path, int]] = frozenset(
    {
        (Path("tests/architecture/test_cognitive_runtime_anti_patterns.py"), 139),
    },
)

SUPPRESSION_CHECKS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("# noqa", NOQA_WITH_REASON_RE),
    ("# type: ignore", TYPE_IGNORE_WITH_REASON_RE),
    ("# pyright: ignore", PYRIGHT_IGNORE_WITH_REASON_RE),
)


def _python_files() -> tuple[Path, ...]:
    """Return files checked for documented suppression usage."""
    files: list[Path] = []
    for root in SUPPRESSION_ROOTS:
        files.extend(root.rglob("*.py"))
    return tuple(sorted(files))


def test_suppressions_require_rule_codes_and_reasons_in_exception_zones() -> None:
    """Allowed suppressions outside protected layers must include rule codes and reasons."""
    violations: list[str] = []

    for path in _python_files():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if (path, line_number) in ALLOWED_UNREASONED_SUPPRESSION_LINES:
                continue
            for token, pattern in SUPPRESSION_CHECKS:
                if token not in line:
                    continue
                if pattern.search(line) is None:
                    violations.append(f"{path}:{line_number}: {line.strip()}")

    assert not violations, "suppressions require rule code and reason:\n" + "\n".join(
        violations,
    )
