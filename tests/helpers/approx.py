"""Test helper for approximate equality assertions.

Wraps :func:`pytest.approx` with renamed keyword-only parameters so
that ``ruff`` boolean-trap rules do not fire on the mirrored signature.
"""

from __future__ import annotations

from typing import Any

import pytest


def approx(
    expected: object,
    rel: float | None = None,
    *,
    absolute_tolerance: float | None = None,
    allow_nan_equal: bool | None = None,
) -> object:
    """Assert approximate equality using ``pytest.approx``.

    Args:
        expected: Expected scalar, sequence, or mapping.
        rel: Optional relative tolerance.
        absolute_tolerance: Optional absolute tolerance.
        allow_nan_equal: Whether NaN values are treated as equal.

    Returns:
        A pytest approx wrapper suitable for ``==`` comparison.
    """
    raw: Any = pytest.approx(  # pyright: ignore[reportUnknownMemberType]  # pytest.approx stubs are incomplete; wrapped in helper
        expected,
        rel=rel,
        abs=absolute_tolerance,
        nan_ok=allow_nan_equal if allow_nan_equal is not None else False,
    )
    return raw
