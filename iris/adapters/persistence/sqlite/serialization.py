"""Shared SQLite serialization helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Callable


def optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


def optional_new_type[IdT: str](
    type_constructor: Callable[[str], IdT],
    value: object | None,
) -> IdT | None:
    if value is None:
        return None
    return type_constructor(str(value))


def datetime_to_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def required_datetime_to_text(value: datetime) -> str:
    return value.isoformat()


def text_to_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def optional_datetime(value: object | None) -> datetime | None:
    if value is None:
        return None
    return text_to_datetime(str(value))
