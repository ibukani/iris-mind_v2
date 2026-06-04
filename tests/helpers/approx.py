"""Typed test helper for approximate equality assertions.

Wraps :func:`pytest.approx` with explicit overloads so static type checkers
can resolve the return type without relying on the untyped third-party stubs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, overload

import pytest

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from _pytest.python_api import ApproxBase


@overload
def approx(expected: float) -> ApproxBase: ...


@overload
def approx(
    expected: float,
    rel: float | None = ...,
    abs: float | None = ...,
    nan_ok: bool = ...,  # noqa: FBT001 -- mirrors pytest.approx signature
) -> ApproxBase: ...


@overload
def approx(expected: Sequence[float]) -> ApproxBase: ...


@overload
def approx(
    expected: Sequence[float],
    rel: float | None = ...,
    abs: float | None = ...,
    nan_ok: bool = ...,  # noqa: FBT001 -- mirrors pytest.approx signature
) -> ApproxBase: ...


@overload
def approx(expected: Mapping[str, float]) -> ApproxBase: ...


@overload
def approx(
    expected: Mapping[str, float],
    rel: float | None = ...,
    abs: float | None = ...,
    nan_ok: bool = ...,  # noqa: FBT001 -- mirrors pytest.approx signature
) -> ApproxBase: ...


@overload
def approx(expected: object) -> ApproxBase: ...


@overload
def approx(
    expected: object,
    rel: float | None = ...,
    abs: float | None = ...,
    nan_ok: bool = ...,  # noqa: FBT001 -- mirrors pytest.approx signature
) -> ApproxBase: ...


def approx(
    expected: object,
    rel: float | None = None,
    abs: float | None = None,  # noqa: A002 -- mirrors pytest.approx signature
    nan_ok: bool = False,  # noqa: FBT001,FBT002 -- mirrors pytest.approx signature
) -> ApproxBase:
    """Assert approximate equality using ``pytest.approx`` with typed overloads.

    Args:
        expected: Expected scalar, sequence, or mapping.
        rel: Optional relative tolerance.
        abs: Optional absolute tolerance.
        nan_ok: Whether NaN values are treated as equal.

    Returns:
        ApproxBase: A pytest approx wrapper suitable for ``==`` comparison.
    """
    raw: ApproxBase = pytest.approx(expected, rel=rel, abs=abs, nan_ok=nan_ok)
    return raw
