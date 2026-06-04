# Copyright 2025 Iris Mind
"""Irisプロジェクト全体で使用するカスタム例外クラス。"""

from __future__ import annotations

from typing import override


class IrisError(Exception):
    """全Irisカスタム例外の基底クラス。"""

    def __init__(self, message: str, code: str | None = None) -> None:
        """メッセージとオプションのコードでエラーを初期化する。

        Args:
            message: Human-readable error description.
            code: Optional error code for debugging and logging.
        """
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__

    @override
    def __str__(self) -> str:
        """オプションのエラーコード接頭辞付きでエラーメッセージを返す。

        Returns:
            str: フォーマットされたエラーメッセージ。
        """
        if self.code != self.__class__.__name__:
            return f"[{self.code}] {self.message}"
        return self.message


class IrisConfigError(IrisError):
    """設定ファイルの読み込みまたは検証エラー。"""


class IrisRuntimeError(IrisError):
    """実行中の予期しない状態遷移のランタイムエラー。"""


class IrisConnectionError(IrisError):
    """外部接続エラー（例：LLMプロバイダ接続失敗）。"""


class IrisMemoryError(IrisError):
    """メモリレイヤエラー（例：ファイル操作またはパース失敗）。"""


class IrisToolError(IrisError):
    """ツールまたは能力の実行エラー。"""


class IrisSessionError(IrisError):
    """セッション管理エラー（例：重複または無効なsession_id）。"""


class IrisLLMError(IrisConnectionError):
    """LLMプロバイダ固有エラー（例：接続失敗、タイムアウト、レート制限）。"""


class IrisLLMUnavailableError(IrisLLMError):
    """LLMプロバイダが利用不可（未実行、キー欠落等）。"""


class IrisCapabilityError(IrisToolError):
    """能力またはツールが利用不可または非サポート。"""
