"""ランタイム設定の共通検証ヘルパー。"""

from __future__ import annotations

import pytest

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.validation import require_greater_than_zero, require_zero_or_greater
from tests.helpers.approx import approx


def test_require_greater_than_zero_accepts_positive_int() -> None:
    """正の整数はそのまま返す。"""
    assert require_greater_than_zero(1, "x") == 1


def test_require_greater_than_zero_accepts_positive_float() -> None:
    """正の float はそのまま返す。"""
    assert require_greater_than_zero(1.5, "x") == approx(1.5)


@pytest.mark.parametrize("value", [0, -1])
def test_require_greater_than_zero_rejects_non_positive_int(value: int) -> None:
    """0 以下の整数は拒否する。"""
    with pytest.raises(ConfigError, match="must be greater than zero"):
        require_greater_than_zero(value, "x")


@pytest.mark.parametrize("value", [0.0, -1.5])
def test_require_greater_than_zero_rejects_non_positive_float(value: float) -> None:
    """0 以下の float は拒否する。"""
    with pytest.raises(ConfigError, match="must be greater than zero"):
        require_greater_than_zero(value, "x")


def test_require_zero_or_greater_accepts_zero_int() -> None:
    """0 の整数はそのまま返す。"""
    assert require_zero_or_greater(0, "x") == 0


def test_require_zero_or_greater_accepts_positive_float() -> None:
    """正の float はそのまま返す。"""
    assert require_zero_or_greater(2.5, "x") == approx(2.5)


@pytest.mark.parametrize("value", [-1, -2])
def test_require_zero_or_greater_rejects_negative_int(value: int) -> None:
    """負の整数は拒否する。"""
    with pytest.raises(ConfigError, match="must be zero or greater"):
        require_zero_or_greater(value, "x")


@pytest.mark.parametrize("value", [-0.1, -3.5])
def test_require_zero_or_greater_rejects_negative_float(value: float) -> None:
    """負の float は拒否する。"""
    with pytest.raises(ConfigError, match="must be zero or greater"):
        require_zero_or_greater(value, "x")
