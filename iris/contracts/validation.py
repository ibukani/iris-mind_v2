"""Contract model 間で共有する入力検証。"""

from __future__ import annotations


def require_non_empty_id(value: str, field_name: str) -> None:
    """NewType ID の空文字を拒否する。

    Raises:
        ValueError: ID が空文字の場合。
    """
    if not value:
        message = f"{field_name} must not be blank"
        raise ValueError(message)
