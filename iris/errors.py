"""Iris プロジェクト全体で使用するカスタム例外群。

トレーサビリティと例外処理の一貫性を向上させるため、
プロジェクト固有の例外をここで定義する。
"""

from __future__ import annotations


class IrisException(Exception):
    """Iris プロジェクトの全カスタム例外の基底クラス。

    Args:
        message: エラーメッセージ。
        code: エラーコード（オプション、デバッグ/ロギング用）。
    """

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__

    def __str__(self) -> str:
        if self.code != self.__class__.__name__:
            return f"[{self.code}] {self.message}"
        return self.message


class IrisConfigError(IrisException):
    """設定ファイル読み込みまたは検証エラー。

    config.yaml の不正な値、必須項目の欠落、
    モデル名の不正値などが対象。
    """


class IrisRuntimeError(IrisException):
    """実行時エラー。実行中の予期しない状態遷移など。"""


class IrisConnectionError(IrisException):
    """外部接続エラー。LLM プロバイダへの接続失敗など。"""


class IrisMemoryError(IrisException):
    """記憶レイヤーのエラー（ファイル操作失敗、パース失敗など）。"""


class IrisToolError(IrisException):
    """ツール（capability）実行エラー。ツール未発見、実行失敗など。"""


class IrisSessionError(IrisException):
    """セッション管理エラー。セッション重複、無効な session_id など。"""


class IrisLLMError(IrisConnectionError):
    """LLM プロバイダ固有エラー。

    Ollama/OpenRouter への接続失敗、タイムアウト、
    レート制限など。
    """


class IrisLLMUnavailableError(IrisLLMError):
    """LLM プロバイダが利用不可（起動していない、キーなし等）。"""


class IrisCapabilityError(IrisToolError):
    """Capability（ツール）が利用不可またはサポート外。"""
