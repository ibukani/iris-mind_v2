"""scripts/check_suppression_debt_changes.py の回帰テスト。

CI で ``origin/main`` が checkout されていない浅い履歴でも merge-base
ガードが致命的に失敗せず、``main`` 候補にフォールバックして最終的に
None を返す経路を保証する。
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers.private_access import import_private_matching, is_callable

if TYPE_CHECKING:
    from collections.abc import Sequence


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    """_run_command 戻り値用の簡易 CompletedProcess モックを返す。

    Returns:
        ``subprocess.run`` の戻り値を模した ``MagicMock`` インスタンス。
    """
    return MagicMock(stdout=stdout, stderr=stderr, returncode=returncode)


# プライベート関数参照は helpers.private_access 経由で取得して ruff/pyright の
# private-member 警告を避ける。
_git_probe: Any = import_private_matching(
    "scripts.check_suppression_debt_changes",
    "_git_probe",
    is_callable,
)
_resolve_merge_base: Any = import_private_matching(
    "scripts.check_suppression_debt_changes",
    "_resolve_merge_base",
    is_callable,
)
_detect_debt_changes: Any = import_private_matching(
    "scripts.check_suppression_debt_changes",
    "_detect_debt_changes",
    is_callable,
)
_git: Any = import_private_matching(
    "scripts.check_suppression_debt_changes",
    "_git",
    is_callable,
)


# scripts.check_suppression_debt_changes._run_command を ``_git`` / ``_git_probe``
# 単位でスタブするための patch ターゲット。文字列で参照して ruff の
# private-member 警告を避ける。
_RUN_COMMAND_TARGET = "scripts.check_suppression_debt_changes._run_command"


class TestGitProbe:
    """_git_probe の戻り値契約テスト。"""

    def test_returns_true_when_ref_exists(self) -> None:
        with patch(_RUN_COMMAND_TARGET, return_value=_completed("abc123\n")):
            found, stdout = _git_probe("rev-parse", "--verify", "origin/main")
        assert found is True
        assert stdout == "abc123"

    def test_returns_false_when_ref_missing(self) -> None:
        with patch(_RUN_COMMAND_TARGET, return_value=_completed("", "", returncode=1)):
            found, stdout = _git_probe("rev-parse", "--verify", "--quiet", "origin/main")
        assert found is False
        assert not stdout

    def test_returns_false_when_stdout_empty(self) -> None:
        with patch(_RUN_COMMAND_TARGET, return_value=_completed("\n  \n", "", returncode=0)):
            found, stdout = _git_probe("rev-parse", "--verify", "--quiet", "origin/main")
        assert found is False
        assert not stdout


class TestResolveMergeBaseFallback:
    """_resolve_merge_base のフォールバック動作回帰テスト。"""

    def test_origin_main_used_when_present(self) -> None:
        responses: Sequence[MagicMock] = (
            _completed("origin_main_sha\n"),
            _completed("merge_base_sha\n"),
        )
        with patch(_RUN_COMMAND_TARGET, side_effect=list(responses)) as mock_run:
            result = _resolve_merge_base()
        assert result == "merge_base_sha"
        assert mock_run.call_count == 2
        # 1 番目: rev-parse origin/main
        assert mock_run.call_args_list[0].args[0][-1] == "origin/main"
        # 2 番目: merge-base HEAD origin/main
        assert mock_run.call_args_list[1].args[0][-1] == "origin/main"

    def test_falls_back_to_local_main_when_origin_missing(self) -> None:
        responses: Sequence[MagicMock] = (
            _completed("", "", returncode=1),
            _completed("local_main_sha\n"),
            _completed("merge_base_sha\n"),
        )
        with patch(_RUN_COMMAND_TARGET, side_effect=list(responses)) as mock_run:
            result = _resolve_merge_base()
        assert result == "merge_base_sha"
        assert mock_run.call_count == 3
        assert mock_run.call_args_list[0].args[0][-1] == "origin/main"
        assert mock_run.call_args_list[1].args[0][-1] == "main"
        # 3 番目は main との merge-base
        assert mock_run.call_args_list[2].args[0][-1] == "main"

    def test_returns_none_when_no_candidate_exists(self) -> None:
        responses: Sequence[MagicMock] = (
            _completed("", "", returncode=1),
            _completed("", "", returncode=1),
        )
        with patch(_RUN_COMMAND_TARGET, side_effect=list(responses)) as mock_run:
            result = _resolve_merge_base()
        assert result is None
        assert mock_run.call_count == 2

    def test_skips_candidate_when_merge_base_fails(self) -> None:
        # origin/main は解決するが merge-base が空 -> main に進む
        responses: Sequence[MagicMock] = (
            _completed("origin_main_sha\n"),
            _completed("", "", returncode=1),
            _completed("local_main_sha\n"),
            _completed("fallback_sha\n"),
        )
        with patch(_RUN_COMMAND_TARGET, side_effect=list(responses)):
            result = _resolve_merge_base()
        assert result == "fallback_sha"


class TestDetectDebtChangesWithoutBase:
    """_detect_debt_changes は merge-base 不在時に空リストを返すこと。"""

    def test_returns_empty_list_and_skips_diff(self) -> None:
        captured = io.StringIO()
        responses: Sequence[MagicMock] = (
            _completed("", "", returncode=1),
            _completed("", "", returncode=1),
        )
        with (
            patch(_RUN_COMMAND_TARGET, side_effect=list(responses)),
            patch("sys.stdout", new=captured),
        ):
            result = _detect_debt_changes()
        assert result == []
        assert "skipping merge-base diff check" in captured.getvalue()

    def test_uses_base_when_available(self) -> None:
        responses: Sequence[MagicMock] = (
            _completed("origin_main_sha\n"),
            _completed("merge_base_sha\n"),
            _completed(
                "M\tscripts/other.py\nM\t.agents/approved-suppression-debt.toml\nA\tsome_new_file.py\n"
            ),
        )
        with patch(_RUN_COMMAND_TARGET, side_effect=list(responses)) as mock_run:
            result = _detect_debt_changes()
        assert len(result) == 1
        assert result[0].path == ".agents/approved-suppression-debt.toml"
        assert result[0].status == "M"
        # diff 呼び出しの引数に merge-base コミットが含まれること
        diff_call = mock_run.call_args_list[2].args[0]
        assert any("merge_base_sha" in str(part) for part in diff_call)


class TestGitStillRaisesOnRealError:
    """_git は ref 探索以外では従来通り非ゼロ終了で例外を送出すること。"""

    def test_git_raises_on_nonzero_exit(self) -> None:
        with (
            patch(_RUN_COMMAND_TARGET, return_value=_completed("", "boom", returncode=2)),
            pytest.raises(RuntimeError, match="exit code 2"),
        ):
            _git("diff", "...")
