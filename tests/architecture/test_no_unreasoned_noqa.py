"""Architecture guard for documented noqa usage in exception zones."""

from __future__ import annotations

from pathlib import Path
import re

NOQA_ROOTS: tuple[Path, ...] = (
    Path("iris/adapters"),
    Path("scripts"),
)

NOQA_WITH_REASON_RE = re.compile(
    r"# noqa:\s*[A-Z]+[0-9]+(?:\s*,\s*[A-Z]+[0-9]+)*\s+--\s+\S+",
)


def _python_files() -> tuple[Path, ...]:
    """Return adapter and script files checked for documented noqa usage."""
    files: list[Path] = []
    for root in NOQA_ROOTS:
        files.extend(root.rglob("*.py"))
    return tuple(sorted(files))


def test_noqa_in_adapters_and_scripts_requires_rule_codes_and_reason() -> None:
    """Allowed noqa comments in exception zones must include rule codes and reasons."""
    violations: list[str] = []

    for path in _python_files():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "# noqa" not in line:
                continue
            if NOQA_WITH_REASON_RE.search(line) is None:
                violations.append(f"{path}:{line_number}: {line.strip()}")

    assert not violations, "noqa in adapters/scripts requires rule code and reason:\n" + "\n".join(
        violations,
    )
