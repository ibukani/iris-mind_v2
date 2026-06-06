"""ランタイム設定のエラー型。"""

from __future__ import annotations


class ConfigError(RuntimeError):
    """ランタイム設定が無効な場合に送出される。"""
