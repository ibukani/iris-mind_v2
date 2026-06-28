"""Shared SQLite serialization helpers."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def optional_text(value: object | None) -> str | None:
    """Nullable DB値を文字列へ変換する。

    Returns:
        文字列またはNone。
    """
    if value is None:
        return None
    return str(value)


def optional_new_type[IdT: str](
    type_constructor: Callable[[str], IdT],
    value: object | None,
) -> IdT | None:
    """Nullable DB値を文字列NewTypeへ変換する。

    Returns:
        変換済みIDまたはNone。
    """
    if value is None:
        return None
    return type_constructor(str(value))


def datetime_to_text(value: datetime | None) -> str | None:
    """Nullable datetimeをISO 8601文字列へ変換する。

    Returns:
        ISO 8601文字列またはNone。
    """
    if value is None:
        return None
    return value.isoformat()


def required_datetime_to_text(value: datetime) -> str:
    """必須datetimeをISO 8601文字列へ変換する。

    Returns:
        ISO 8601文字列。
    """
    return value.isoformat()


def text_to_datetime(value: str) -> datetime:
    """ISO 8601文字列をdatetimeへ変換する。

    Returns:
        復元したdatetime。
    """
    return datetime.fromisoformat(value)


def optional_datetime(value: object | None) -> datetime | None:
    """Nullable DB値をdatetimeへ変換する。

    Returns:
        復元したdatetimeまたはNone。
    """
    if value is None:
        return None
    return text_to_datetime(str(value))
