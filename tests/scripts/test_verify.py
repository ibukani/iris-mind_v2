"""scripts/verify.py の失敗分析統合テスト。"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import ANY, MagicMock, patch

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
from scripts.verify import (
    CHECKS,
    RECOMMENDATIONS,
    Check,
    main,
    run_check,
    selected_checks,
)

from tests.helpers.private_access import import_private_matching, is_callable

_first_failing_location: Any = import_private_matching(
    "scripts.verify", "_first_failing_location", is_callable
)


class TestFirstFailingLocation:
    """_first_failing_location の正規表現抽出テスト。"""

    def test_extracts_supported_failure_shapes(self) -> None:
        """主要 checker の first failure を抽出する。"""
        cases = {
            "FAILED tests/runtime/test_config.py::test_parse - assert 0 == 1": (
                "tests/runtime/test_config.py::test_parse"
            ),
            "iris/core/utils.py:42:5: E501 Line too long": "iris/core/utils.py:42",
            "iris/core/utils.py:42: error: Incompatible types": "iris/core/utils.py:42",
            "/workspace/iris/core/utils.py:42:5 - error: Type mismatch": (
                "/workspace/iris/core/utils.py:42"
            ),
            "iris/core/utils.py\niris/core/other.py\n": "iris/core/utils.py",
        }
        for stdout, expected in cases.items():
            assert _first_failing_location(stdout) == expected

    def test_pytest_priority_over_file_line(self) -> None:
        """FAILED パターンが file:line パターンより優先されることを確認する。"""
        stdout = (
            "iris/core/utils.py:1: error: unrelated\n"
            "FAILED tests/runtime/test_config.py::test_parse - assert 0 == 1\n"
            "iris/core/other.py:10: error: another"
        )
        result = _first_failing_location(stdout)
        assert result == "tests/runtime/test_config.py::test_parse"

    def test_no_match(self) -> None:
        assert _first_failing_location("") is None
        assert _first_failing_location("no errors here") is None


class TestCheckDefinitions:
    """Check dataclass と CHECKS 設定のテスト。"""

    def test_check_contracts(self) -> None:
        """定義済み checks は名前と recommendation を揃える。"""
        names = {check.name for check in CHECKS}
        expected = {
            "lint",
            "format",
            "type",
            "pyright",
            "debt-registry",
            "architecture",
            "test-budget",
            "tests+coverage",
            "e2e",
        }
        assert names == expected
        assert {check.failure_class for check in CHECKS}.issubset(set(RECOMMENDATIONS))


class TestRunCheckOutput:
    """run_check 失敗分析出力フォーマットのテスト。"""

    def test_success_output(self) -> None:
        check = Check("lint", ("echo", "hello"), failure_class="lint")
        with patch("scripts.verify._run_command") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        captured = io.StringIO()
        with patch("sys.stdout", new=captured):
            result = run_check(check)
        assert result == 0
        assert "passed" in captured.getvalue()

    def test_streaming_check_does_not_capture_output(self) -> None:
        check = Check(
            "tests+coverage",
            ("pytest", "tests"),
            failure_class="tests+coverage",
            stream_output=True,
        )
        with patch("scripts.verify._run_command") as mock_run:
            mock_run.return_value = MagicMock(stdout=None, stderr=None, returncode=0)

            captured = io.StringIO()
            with patch("sys.stdout", new=captured):
                result = run_check(check)

        assert result == 0
        mock_run.assert_called_once_with(
            check.command,
            cwd=ANY,
            check=False,
            capture_output=False,
            text=True,
        )
        assert "passed" in captured.getvalue()

    def test_streaming_check_failure_with_stdout_none_prints_fallback_hint(self) -> None:
        """stdout=None (streaming) の失敗時は fallback hint を出力する。"""
        check = Check(
            "tests+coverage",
            ("pytest", "tests"),
            failure_class="tests+coverage",
            stream_output=True,
        )
        with patch("scripts.verify._run_command") as mock_run:
            mock_run.return_value = MagicMock(stdout=None, stderr=None, returncode=1)

            captured = io.StringIO()
            with patch("sys.stdout", new=captured):
                result = run_check(check)

        assert result == 1
        output = captured.getvalue()
        assert "failed with exit code 1" in output
        assert "class: tests+coverage" in output
        assert "first failure: unavailable because output was streamed" in output
        assert "make ai-test-target" in output
        assert "first failure:" in output
        # non-streaming "next:" recommendation must NOT appear in streaming path
        assert "make ai-test-target TARGET=<failing_test>  OR  make coverage" not in output

    def test_failure_output(self) -> None:
        check = Check(
            "lint",
            ("uv", "run", "ruff", "check", "."),
            failure_class="lint",
        )
        with patch("scripts.verify._run_command") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="iris/core/utils.py:42:5: E501 Line too long\n",
                stderr="",
                returncode=1,
            )
            captured = io.StringIO()
            with patch("sys.stdout", new=captured):
                result = run_check(check)
            assert result == 1
            output = captured.getvalue()
            assert "failed with exit code 1" in output
            assert "class: lint" in output
            assert "first failure: iris/core/utils.py:42" in output
            assert "next:" in output
            assert "do not relax config" in output

    def test_failure_with_stderr(self) -> None:
        check = Check("type", ("mypy", "."), failure_class="type")
        with patch("scripts.verify._run_command") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="",
                stderr="mypy: command not found\n",
                returncode=1,
            )
            captured = io.StringIO()
            with patch("sys.stdout", new=captured):
                result = run_check(check)
            assert result == 1
            output = captured.getvalue()
            assert "mypy: command not found" in output
            assert "class: type" in output


def test_main_failure_summary_output() -> None:
    """main() --keep-going 時の最終失敗サマリー出力テスト。"""
    with patch("scripts.verify._run_command") as mock_run:
        mock_run.return_value = MagicMock(stdout="error\n", stderr="", returncode=1)
        captured = io.StringIO()
        with patch("sys.stdout", new=captured):
            exit_code = main(["--keep-going"])
        assert exit_code == 1
        output = captured.getvalue()
        assert "Verification failed:" in output
        assert "Failure-analysis summary:" in output
        assert "- lint (lint):" in output


def test_main_passed_summary() -> None:
    """main() 全チェック通過時の出力テスト。"""
    with patch("scripts.verify._run_command") as mock_run:
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        captured = io.StringIO()
        with patch("sys.stdout", new=captured):
            exit_code = main([])
        assert exit_code == 0
        assert "Verification passed." in captured.getvalue()


class TestSelectedChecks:
    """selected_checks のフィルタリングテスト。"""

    def test_selected_check_sets(self) -> None:
        """Quick/full の check selection をまとめて検証する。"""
        quick_names = {check.name for check in selected_checks(quick=True)}
        full_names = {check.name for check in selected_checks(quick=False)}
        expected_full = {
            "lint",
            "format",
            "type",
            "pyright",
            "debt-registry",
            "architecture",
            "test-budget",
            "tests+coverage",
            "e2e",
        }
        assert "architecture" in quick_names
        assert "tests+coverage" not in quick_names
        assert "e2e" not in quick_names
        assert full_names == expected_full
        arch_check = next(c for c in CHECKS if c.name == "architecture")
        assert arch_check.command == ("make", "static-arch")

    def test_e2e_command_uses_tests_e2e_and_excludes_llm_live(self) -> None:
        """e2e チェックのコマンドは tests/e2e を使い llm_live を除外する。"""
        e2e_check = next(c for c in CHECKS if c.name == "e2e")
        command_str = " ".join(e2e_check.command)
        assert "tests/e2e" in command_str
        assert "not llm_live" in command_str


class TestTestBudget:
    """scripts/check_test_budget.py のテスト。"""

    def test_parse_and_enforce_budget(self) -> None:
        """Collection 集計と上限判定をまとめて検証する。"""
        summary_output = "tests/runtime/test_config.py: 45\ntests/scripts/test_verify.py: 24\n"
        nodeid_output = (
            "tests/runtime/test_config.py::test_a\n"
            "tests/runtime/test_config.py::test_b[param]\n"
            "tests/scripts/test_verify.py::TestThing::test_c\n"
        )

        assert parse_collection_summary(summary_output) == CollectionStats(files=2, items=69)
        assert parse_collection_summary(nodeid_output) == CollectionStats(files=2, items=3)
        enforce_budget(
            CollectionStats(
                files=MAX_DEFAULT_TEST_FILES,
                items=MAX_DEFAULT_TEST_ITEMS,
            )
        )
        with pytest.raises(BudgetError, match="exceeds budget"):
            enforce_budget(
                CollectionStats(
                    files=MAX_DEFAULT_TEST_FILES + 1,
                    items=MAX_DEFAULT_TEST_ITEMS,
                )
            )

    def test_collect_default_tests_raises_on_collection_failure(self) -> None:
        """Pytest collect 自体が失敗した場合は明示エラーにする。"""
        completed = MagicMock(stdout="bad collect\n", stderr="boom\n", returncode=2)
        with (
            patch("scripts.check_test_budget._run_command", return_value=completed),
            pytest.raises(RuntimeError, match="pytest collection failed"),
        ):
            collect_default_tests(("tests/broken",))
