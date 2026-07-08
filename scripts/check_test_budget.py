"""Guard default pytest collection size before the slow coverage gate."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import TYPE_CHECKING

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._subprocess_runner import run as _run_command

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_TEST_TARGETS: tuple[str, ...] = (
    "tests/adapters",
    "tests/architecture",
    "tests/cognitive",
    "tests/contracts",
    "tests/core",
    "tests/features",
    "tests/presentation",
    "tests/runtime",
    "tests/scripts",
    "tests/test_oneturn_flow.py",
)
MAX_DEFAULT_TEST_FILES = 305
MAX_DEFAULT_TEST_ITEMS = 2150

_COLLECT_LINE = re.compile(r"^.+?: (?P<count>\d+)$")


@dataclass(frozen=True)
class TestCollectionStats:
    """Default pytest collection size."""

    files: int
    items: int


class TestBudgetError(RuntimeError):
    """Default pytest collection exceeded the repository budget."""


def parse_collection_summary(output: str) -> TestCollectionStats:
    """Parse ``pytest --collect-only -q`` per-file summary output.

    Args:
        output: Captured pytest collection output.

    Returns:
        TestCollectionStats: Number of test files and collected items.
    """
    files = 0
    items = 0
    for line in output.splitlines():
        match = _COLLECT_LINE.match(line.strip())
        if match is None:
            continue
        files += 1
        items += int(match.group("count"))
    return TestCollectionStats(files=files, items=items)


def enforce_budget(stats: TestCollectionStats) -> None:
    """Fail when default test collection grows past the approved budget.

    Args:
        stats: Default pytest collection size.

    Raises:
        TestBudgetError: Collection exceeds the file or item budget.
    """
    if stats.files <= MAX_DEFAULT_TEST_FILES and stats.items <= MAX_DEFAULT_TEST_ITEMS:
        return
    message = (
        f"default pytest collection exceeds budget: {stats.files}/{MAX_DEFAULT_TEST_FILES} "
        f"files, {stats.items}/{MAX_DEFAULT_TEST_ITEMS} items. Merge duplicate tests or "
        f"intentionally update the budget with review."
    )
    raise TestBudgetError(message)


def collect_default_tests(targets: Sequence[str] = DEFAULT_TEST_TARGETS) -> TestCollectionStats:
    """Collect default non-E2E tests and return size stats.

    Args:
        targets: Pytest target paths.

    Returns:
        TestCollectionStats: Number of test files and collected items.

    Raises:
        RuntimeError: Pytest collection fails.
    """
    command = ("uv", "run", "pytest", *targets, "--collect-only", "-q")
    completed = _run_command(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        output = (completed.stdout or "") + (completed.stderr or "")
        message = f"pytest collection failed with exit code {completed.returncode}\n{output}"
        raise RuntimeError(message)
    return parse_collection_summary(completed.stdout or "")


def main() -> int:
    """Run the default test collection budget guard.

    Returns:
        Zero when the collection is within budget, one otherwise.
    """
    try:
        stats = collect_default_tests()
        enforce_budget(stats)
    except (RuntimeError, TestBudgetError) as exc:
        sys.stdout.write(f"{exc}\n")
        return 1
    message = (
        f"default pytest collection within budget: {stats.files}/{MAX_DEFAULT_TEST_FILES} "
        f"files, {stats.items}/{MAX_DEFAULT_TEST_ITEMS} items\n"
    )
    sys.stdout.write(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
