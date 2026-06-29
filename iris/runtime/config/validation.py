"""ランタイム設定向けの共通値検証ヘルパー。"""

from __future__ import annotations

from iris.runtime.config.errors import ConfigError


def require_greater_than_zero[NumberT: int | float](
    value: NumberT,
    path: str,
) -> NumberT:
    """値が 0 より大きいことを検証する。

    Args:
        value: 検証対象の数値。
        path: エラーメッセージに含める設定パス。

    Returns:
        検証済みの値。

    """
    return _require_number_bound(value, path, allow_zero=False)


def require_zero_or_greater[NumberT: int | float](
    value: NumberT,
    path: str,
) -> NumberT:
    """値が 0 以上であることを検証する。

    Args:
        value: 検証対象の数値。
        path: エラーメッセージに含める設定パス。

    Returns:
        検証済みの値。

    """
    return _require_number_bound(value, path, allow_zero=True)


def _require_number_bound[NumberT: int | float](
    value: NumberT,
    path: str,
    *,
    allow_zero: bool,
) -> NumberT:
    """数値の下限を検証する。

    Args:
        value: 検証対象の数値。
        path: エラーメッセージに含める設定パス。
        allow_zero: 0 を許可するなら True。

    Returns:
        検証済みの値。

    Raises:
        ConfigError: 値が下限を満たさない場合。
    """
    if isinstance(value, bool):
        message = f"{path} must be {'zero or greater' if allow_zero else 'greater than zero'}"
        raise ConfigError(message)
    if allow_zero:
        if value < 0:
            message = f"{path} must be zero or greater"
            raise ConfigError(message)
    elif value <= 0:
        message = f"{path} must be greater than zero"
        raise ConfigError(message)
    return value
