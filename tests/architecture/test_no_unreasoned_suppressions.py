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
    r"# noqa:\s*[A-Z]+[0-9]+(?:\s*,\s*[A-Z]+[0-9]+)*(?:\s+--|\s+#)\s+\S+",
)
TYPE_IGNORE_WITH_REASON_RE = re.compile(
    r"# type:\s*ignore\[[a-z0-9\-,]+\](?:\s+--|\s+#)\s+\S+",
)
PYRIGHT_IGNORE_WITH_REASON_RE = re.compile(
    r"# pyright:\s*ignore\[[A-Za-z0-9_,]+\](?:\s+--|\s+#)\s+\S+",
)

# Files that DEFINE the suppression tokens and regex patterns used by the
# architecture scanners. They necessarily contain literal suppression token
# strings as test fixtures and are excluded from the documented-suppression
# check entirely. Do not add production code or behavioural tests here.
SCANNER_FIXTURE_FILES: frozenset[Path] = frozenset(
    {
        Path("tests/architecture/test_no_unreasoned_suppressions.py"),
        Path("tests/architecture/test_no_unapproved_suppressions.py"),
        Path("tests/architecture/test_no_file_level_suppressions.py"),
    },
)

# New suppressions in exception zones (iris/adapters, scripts, tests) MUST
# include a rule code and a reason. There are no grandfathered lines: every
# real suppression comment is expected to follow the format enforced below.
ALLOWED_UNREASONED_SUPPRESSION_LINES: frozenset[tuple[Path, int]] = frozenset()

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
        if path in SCANNER_FIXTURE_FILES:
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for token, pattern in SUPPRESSION_CHECKS:
                if token not in line:
                    continue
                if pattern.search(line) is None:
                    violations.append(f"{path}:{line_number}: {line.strip()}")

    assert not violations, "suppressions require rule code and reason:\n" + "\n".join(
        violations,
    )
