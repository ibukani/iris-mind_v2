"""Import prefix 判定 helper。"""

from __future__ import annotations


def matches_prefix(value: str, prefix: str) -> bool:
    """Value が prefix module またはその子 module なら True。

    Returns:
        Match result。
    """
    return value == prefix or value.startswith(f"{prefix}.")


def matches_any_prefix(value: str, prefixes: set[str] | frozenset[str]) -> bool:
    """Value がいずれかの prefix に一致するなら True。

    Returns:
        Match result。
    """
    return any(matches_prefix(value, prefix) for prefix in prefixes)
