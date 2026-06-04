from collections.abc import Mapping, Sequence
from typing import overload

class ApproxBase: ...

@overload
def approx(expected: float) -> ApproxBase: ...
@overload
def approx(
    expected: float,
    rel: float | None = ...,
    abs: float | None = ...,
    nan_ok: bool = ...,
) -> ApproxBase: ...
@overload
def approx(expected: Sequence[float]) -> ApproxBase: ...
@overload
def approx(
    expected: Sequence[float],
    rel: float | None = ...,
    abs: float | None = ...,
    nan_ok: bool = ...,
) -> ApproxBase: ...
@overload
def approx(expected: Mapping[str, float]) -> ApproxBase: ...
@overload
def approx(
    expected: Mapping[str, float],
    rel: float | None = ...,
    abs: float | None = ...,
    nan_ok: bool = ...,
) -> ApproxBase: ...
@overload
def approx(expected: object) -> ApproxBase: ...
@overload
def approx(
    expected: object,
    rel: float | None = ...,
    abs: float | None = ...,
    nan_ok: bool = ...,
) -> ApproxBase: ...
