"""Datetime parsing utilities."""

from __future__ import annotations

from datetime import UTC, datetime


def parse_datetime(value: object) -> datetime | None:
    """Parse an object into a timezone-aware datetime.

    Args:
        value: A datetime object, ISO format string, or falsy value.

    Returns:
        Parsed datetime, or None if value is falsy.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def now_utc() -> datetime:
    """現在の timezone-aware UTC datetime を返す。

    Returns:
        datetime: timezone-aware な UTC タイムスタンプ。
    """
    return datetime.now(tz=UTC)
