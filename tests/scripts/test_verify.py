"""scripts/verify.py の失敗分析統合テスト。"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

from scripts.verify import (
    CHECKS,
    RECOMMENDATIONS,
    Check,
    main,
    run_check,
    selected_checks,
)

from tests.helpers.private_access import import_private

_first_failing_location = import_private("scripts.verify", "_first_failing_location")


class TestFirstFailingLocation:
    """_first_failing_location の正規表現抽出テスト。"""

    def test_pytest_failed(self) -> None:
        stdout = "FAILED tests/runtime/test_config.py::test_parse - assert 0 == 1"
        result = _first_failing_location(stdout)
        assert result == "tests/runtime/test_config.py::test_parse"

    def test_ruff_lint(self) -> None:
        stdout = "iris/core/utils.py:42:5: E501 Line too long"
        result = _first_failing_location(stdout)
        assert result == "iris/core/utils.py:42"

    def test_mypy_error(self) -> None:
        stdout = "iris/core/utils.py:42: error: Incompatible types"
        result = _first_failing_location(stdout)
        assert result == "iris/core/utils.py:42"

    def test_pyright_error(self) -> None:
        stdout = "/workspace/iris/core/utils.py:42:5 - error: Type mismatch"
        result = _first_failing_location(stdout)
        assert result == "/workspace/iris/core/utils.py:42"

    def test_ruff_format(self) -> None:
        stdout = "iris/core/utils.py\niris/core/other.py\n"
        result = _first_failing_location(stdout)
        assert result == "iris/core/utils.py"

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

    def test_all_checks_have_failure_class(self) -> None:
        for check in CHECKS:
            assert check.failure_class in RECOMMENDATIONS

    def test_expected_check_names(self) -> None:
        names = {check.name for check in CHECKS}
        expected = {
            "lint",
            "format",
            "type",
            "pyright",
            "architecture",
            "tests+coverage",
        }
        assert names == expected

    def test_recommendation_coverage(self) -> None:
        classes = {check.failure_class for check in CHECKS}
        assert classes.issubset(set(RECOMMENDATIONS))


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

    def test_quick_includes_architecture_check(self) -> None:
        """--quick でも architecture チェック（make static-arch）が含まれる。"""
        checks = selected_checks(quick=True)
        names = {check.name for check in checks}
        assert "architecture" in names

    def test_architecture_check_uses_static_arch(self) -> None:
        """Architecture チェックは make static-arch を実行する。"""
        arch_check = next(c for c in CHECKS if c.name == "architecture")
        assert arch_check.command == ("make", "static-arch")

    def test_quick_excludes_tests_coverage(self) -> None:
        """--quick では tests+coverage が除外される。"""
        checks = selected_checks(quick=True)
        names = {check.name for check in checks}
        assert "tests+coverage" not in names

    def test_full_includes_all_checks(self) -> None:
        """Full モードでは全チェックが含まれる。"""
        checks = selected_checks(quick=False)
        names = {check.name for check in checks}
        assert names == {"lint", "format", "type", "pyright", "architecture", "tests+coverage"}
