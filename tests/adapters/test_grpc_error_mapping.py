"""gRPC error mapping for LLM provider errors and runtime exceptions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import grpc
import pytest

from iris.adapters.grpc.mappers import (
    map_exception_to_grpc,
    map_provider_error_to_status,
)
from iris.adapters.llm.diagnostics import (
    LLMProviderAuthenticationError,
    LLMProviderConnectionError,
    LLMProviderError,
    LLMProviderInvalidResponseError,
    LLMProviderModelUnavailableError,
    LLMProviderQuotaError,
    LLMProviderRateLimitError,
    LLMProviderTimeoutError,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def test_connection_error_maps_to_unavailable() -> None:
    """LLMProviderConnectionError → UNAVAILABLE."""
    assert (
        map_provider_error_to_status(LLMProviderConnectionError("conn refused"))
        is grpc.StatusCode.UNAVAILABLE
    )


def test_timeout_error_maps_to_deadline_exceeded() -> None:
    """LLMProviderTimeoutError → DEADLINE_EXCEEDED."""
    assert (
        map_provider_error_to_status(LLMProviderTimeoutError("timed out"))
        is grpc.StatusCode.DEADLINE_EXCEEDED
    )


def test_authentication_error_maps_to_unauthenticated() -> None:
    """LLMProviderAuthenticationError → UNAUTHENTICATED."""
    assert (
        map_provider_error_to_status(LLMProviderAuthenticationError("bad key"))
        is grpc.StatusCode.UNAUTHENTICATED
    )


def test_rate_limit_error_maps_to_resource_exhausted() -> None:
    """LLMProviderRateLimitError → RESOURCE_EXHAUSTED."""
    assert (
        map_provider_error_to_status(LLMProviderRateLimitError("429"))
        is grpc.StatusCode.RESOURCE_EXHAUSTED
    )


def test_quota_error_maps_to_resource_exhausted() -> None:
    """LLMProviderQuotaError → RESOURCE_EXHAUSTED."""
    assert (
        map_provider_error_to_status(LLMProviderQuotaError("quota exceeded"))
        is grpc.StatusCode.RESOURCE_EXHAUSTED
    )


def test_model_unavailable_error_maps_to_failed_precondition() -> None:
    """LLMProviderModelUnavailableError → FAILED_PRECONDITION."""
    assert (
        map_provider_error_to_status(LLMProviderModelUnavailableError("missing model"))
        is grpc.StatusCode.FAILED_PRECONDITION
    )


def test_invalid_response_error_maps_to_internal() -> None:
    """LLMProviderInvalidResponseError → INTERNAL."""
    assert (
        map_provider_error_to_status(LLMProviderInvalidResponseError("bad shape"))
        is grpc.StatusCode.INTERNAL
    )


def test_base_provider_error_maps_to_unknown() -> None:
    """Subclass mismatchの LLMProviderError は UNKNOWN にマップ。"""

    class _CustomProviderError(LLMProviderError):
        pass

    assert map_provider_error_to_status(_CustomProviderError("custom")) is grpc.StatusCode.UNKNOWN


def test_map_exception_returns_status_and_message_for_provider_error() -> None:
    """map_exception_to_grpc は provider error に (status, message) を返す。"""
    status, message = map_exception_to_grpc(LLMProviderConnectionError("conn refused"))

    assert status is grpc.StatusCode.UNAVAILABLE
    assert "provider error" in message
    assert "conn refused" in message


def test_map_exception_returns_internal_for_unrecognized_exception() -> None:
    """map_exception_to_grpc は未知の例外を INTERNAL にマップ。"""
    status, message = map_exception_to_grpc(RuntimeError("boom"))

    assert status is grpc.StatusCode.INTERNAL
    assert message == "runtime service failed"


def test_map_exception_handles_value_error_as_internal() -> None:
    """ValueError のような非 provider exception は INTERNAL にマップ。"""
    status, _ = map_exception_to_grpc(ValueError("bad input"))

    assert status is grpc.StatusCode.INTERNAL


@pytest.mark.parametrize(
    ("error_factory", "expected_status"),
    [
        (lambda: LLMProviderConnectionError("x"), grpc.StatusCode.UNAVAILABLE),
        (lambda: LLMProviderTimeoutError("x"), grpc.StatusCode.DEADLINE_EXCEEDED),
        (lambda: LLMProviderAuthenticationError("x"), grpc.StatusCode.UNAUTHENTICATED),
        (lambda: LLMProviderRateLimitError("x"), grpc.StatusCode.RESOURCE_EXHAUSTED),
        (lambda: LLMProviderQuotaError("x"), grpc.StatusCode.RESOURCE_EXHAUSTED),
        (
            lambda: LLMProviderModelUnavailableError("x"),
            grpc.StatusCode.FAILED_PRECONDITION,
        ),
        (lambda: LLMProviderInvalidResponseError("x"), grpc.StatusCode.INTERNAL),
    ],
)
def test_each_provider_error_subclass_has_a_stable_status(
    error_factory: Callable[[], LLMProviderError],
    expected_status: grpc.StatusCode,
) -> None:
    """Provider error サブクラスごとに安定 status コードが返る。"""
    exc = error_factory()
    assert map_provider_error_to_status(exc) is expected_status
