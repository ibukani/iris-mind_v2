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
from scripts.test_targets import DEFAULT_TEST_TARGETS

if TYPE_CHECKING:
    from collections.abc import Sequence

MAX_DEFAULT_TEST_FILES = 305
MAX_DEFAULT_TEST_ITEMS = 2150

_SUMMARY_LINE = re.compile(r"^.+?: (?P<count>\d+)$")


@dataclass(frozen=True)
class TestCollectionStats:
    """Default pytest collection size."""

    files: int
    items: int


class TestBudgetError(RuntimeError):
    """Default pytest collection exceeded the repository budget."""


def parse_collection_summary(output: str) -> TestCollectionStats:
    """Parse ``pytest --collect-only -q`` output.

    Args:
        output: Captured pytest collection output.

    Returns:
        TestCollectionStats: Number of test files and collected items.
    """
    node_files: set[str] = set()
    node_items = 0
    summary_files = 0
    summary_items = 0
    for line in output.splitlines():
        text = line.strip()
        if not text:
            continue
        node_path = _nodeid_path(text)
        if node_path is not None:
            node_files.add(node_path)
            node_items += 1
            continue
        match = _SUMMARY_LINE.match(text)
        if match is not None:
            summary_files += 1
            summary_items += int(match.group("count"))
    if node_items > 0:
        return TestCollectionStats(files=len(node_files), items=node_items)
    return TestCollectionStats(files=summary_files, items=summary_items)


def _nodeid_path(text: str) -> str | None:
    if "::" not in text:
        return None
    path = text.split("::", maxsplit=1)[0]
    if not path.endswith(".py"):
        return None
    return path


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
