"""scripts/check_test_budget.py のテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from scripts.check_test_budget import (
    MAX_DEFAULT_TEST_FILES,
    MAX_DEFAULT_TEST_ITEMS,
    collect_default_tests,
    enforce_budget,
    parse_collection_summary,
)
from scripts.check_test_budget import TestBudgetError as BudgetError
from scripts.check_test_budget import TestCollectionStats as CollectionStats


def test_parse_collection_summary_counts_files_and_items() -> None:
    """Pytest collect summary から file 数と item 数を集計する。"""
    output = "tests/runtime/test_config.py: 45\ntests/scripts/test_verify.py: 24\n"

    stats = parse_collection_summary(output)

    assert stats == CollectionStats(files=2, items=69)


def test_enforce_budget_accepts_current_budget() -> None:
    """上限内の collection は通す。"""
    enforce_budget(
        CollectionStats(
            files=MAX_DEFAULT_TEST_FILES,
            items=MAX_DEFAULT_TEST_ITEMS,
        )
    )


def test_enforce_budget_rejects_growth() -> None:
    """上限超過は coverage 前に止める。"""
    stats = CollectionStats(
        files=MAX_DEFAULT_TEST_FILES + 1,
        items=MAX_DEFAULT_TEST_ITEMS,
    )

    with pytest.raises(BudgetError, match="exceeds budget"):
        enforce_budget(stats)


def test_collect_default_tests_raises_on_pytest_collection_failure() -> None:
    """Pytest collect 自体が失敗した場合は明示エラーにする。"""
    completed = MagicMock(stdout="bad collect\n", stderr="boom\n", returncode=2)
    with (
        patch("scripts.check_test_budget._run_command", return_value=completed),
        pytest.raises(RuntimeError, match="pytest collection failed"),
    ):
        collect_default_tests(("tests/broken",))
