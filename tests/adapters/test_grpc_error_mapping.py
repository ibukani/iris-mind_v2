"""gRPC error mapping for LLM provider errors and runtime exceptions."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, override
from unittest.mock import AsyncMock

from google.protobuf.timestamp_pb2 import Timestamp
import grpc
import pytest

from iris.adapters.grpc.mappers import (
    GrpcRuntimeMapper,
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

from iris.adapters.grpc.server import IrisRuntimeGrpcServicer
from iris.generated.iris.api.v1 import observations_pb2
from iris.generated.iris.runtime.v1 import runtime_pb2


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


# ---------------------------------------------------------------------------
# gRPC servicer-level tests: provider errors propagate to expected status codes
# ---------------------------------------------------------------------------


def _build_servicer(handle: AsyncMock) -> tuple[IrisRuntimeGrpcServicer, AsyncMock]:
    """Construct a servicer with a mocked runtime service and a fake context.

    Args:
        handle: Async mock that replaces ``runtime_service.handle_observation``.

    Returns:
        Tuple of (servicer, context mock).
    """
    runtime_service = AsyncMock()
    runtime_service.handle_observation = handle
    servicer = IrisRuntimeGrpcServicer(
        runtime_service=runtime_service,
        mapper=GrpcRuntimeMapper(),
    )
    context = AsyncMock()
    context.abort.side_effect = lambda *_args, **_kwargs: _raise_abort()
    return servicer, context


def _raise_abort() -> None:
    """Raise an RpcError to mirror grpc.aio.ServicerContext.abort semantics.

    Raises:
        _abort_error: An ``grpc.RpcError`` sentinel used by tests.
    """
    raise _abort_error()


class _AbortError(grpc.RpcError):
    """A minimal ``grpc.RpcError`` raising helper.

    gRPC's async ``AioRpcError`` enforces a non-None internal metadata type
    in some versions and is awkward to construct in tests. ``_AbortError``
    inherits the abstract ``grpc.RpcError`` and ``code()`` contract by
    raising ``NotImplementedError`` because the tests only use the instance
    as a sentinel value for ``pytest.raises(grpc.RpcError)`` and to
    observe that ``context.abort`` was awaited with the correct code.
    """

    @override
    def code(self) -> grpc.StatusCode:
        """Return the gRPC status code (unused by tests)."""
        raise NotImplementedError

    @override
    def details(self) -> str | None:
        """Return the gRPC error details (unused by tests)."""
        raise NotImplementedError


def _abort_error() -> grpc.RpcError:
    """Build an RpcError suitable for raising from a mocked ServicerContext.

    Returns:
        A ``grpc.RpcError`` instance used purely as a sentinel in tests.
    """
    return _AbortError()


def _build_request() -> runtime_pb2.SubmitObservationRequest:
    """Build a minimal SubmitObservation request proto.

    Returns:
        The request proto with a single observation.
    """
    timestamp = Timestamp()
    timestamp.FromDatetime(datetime.now(UTC))
    request = runtime_pb2.SubmitObservationRequest()
    request.observation.observation_id = "obs-1"
    request.observation.session_id = "sess-1"
    request.observation.kind = observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE
    request.observation.occurred_at.CopyFrom(timestamp)
    request.observation.context.source = "test"
    request.observation.actor_message.text = "hello"
    return request


@pytest.mark.anyio
async def test_servicer_maps_provider_timeout_to_deadline_exceeded() -> None:
    """IrisRuntimeGrpcServicer aborts with DEADLINE_EXCEEDED on provider timeout."""
    servicer, context = _build_servicer(
        AsyncMock(side_effect=LLMProviderTimeoutError("timed out"))
    )

    with pytest.raises(grpc.RpcError):
        await servicer.SubmitObservation(_build_request(), context)

    assert context.abort.await_args.args[0] is grpc.StatusCode.DEADLINE_EXCEEDED


@pytest.mark.anyio
async def test_servicer_maps_provider_connection_error_to_unavailable() -> None:
    """IrisRuntimeGrpcServicer aborts with UNAVAILABLE on provider connection failure."""
    servicer, context = _build_servicer(
        AsyncMock(side_effect=LLMProviderConnectionError("conn refused"))
    )

    with pytest.raises(grpc.RpcError):
        await servicer.SubmitObservation(_build_request(), context)

    assert context.abort.await_args.args[0] is grpc.StatusCode.UNAVAILABLE


@pytest.mark.anyio
async def test_servicer_maps_provider_model_unavailable_to_failed_precondition() -> None:
    """IrisRuntimeGrpcServicer aborts with FAILED_PRECONDITION on model unavailability."""
    servicer, context = _build_servicer(
        AsyncMock(side_effect=LLMProviderModelUnavailableError("no such model"))
    )

    with pytest.raises(grpc.RpcError):
        await servicer.SubmitObservation(_build_request(), context)

    assert context.abort.await_args.args[0] is grpc.StatusCode.FAILED_PRECONDITION


@pytest.mark.anyio
async def test_servicer_maps_provider_rate_limit_to_resource_exhausted() -> None:
    """IrisRuntimeGrpcServicer aborts with RESOURCE_EXHAUSTED on rate limiting."""
    servicer, context = _build_servicer(
        AsyncMock(side_effect=LLMProviderRateLimitError("rate limited"))
    )

    with pytest.raises(grpc.RpcError):
        await servicer.SubmitObservation(_build_request(), context)

    assert context.abort.await_args.args[0] is grpc.StatusCode.RESOURCE_EXHAUSTED


@pytest.mark.anyio
async def test_servicer_maps_provider_authentication_to_unauthenticated() -> None:
    """IrisRuntimeGrpcServicer aborts with UNAUTHENTICATED on auth failure."""
    servicer, context = _build_servicer(
        AsyncMock(side_effect=LLMProviderAuthenticationError("bad key"))
    )

    with pytest.raises(grpc.RpcError):
        await servicer.SubmitObservation(_build_request(), context)

    assert context.abort.await_args.args[0] is grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.anyio
async def test_servicer_maps_unknown_exceptions_to_internal() -> None:
    """Unknown exceptions fall back to INTERNAL."""
    servicer, context = _build_servicer(AsyncMock(side_effect=RuntimeError("boom")))

    with pytest.raises(grpc.RpcError):
        await servicer.SubmitObservation(_build_request(), context)

    assert context.abort.await_args.args[0] is grpc.StatusCode.INTERNAL


@pytest.mark.anyio
async def test_servicer_does_not_swallow_cancellation() -> None:
    """``asyncio.CancelledError`` must propagate without ``abort()`` or INTERNAL mapping."""
    servicer, context = _build_servicer(
        AsyncMock(side_effect=asyncio.CancelledError())
    )

    with pytest.raises(asyncio.CancelledError):
        await servicer.SubmitObservation(_build_request(), context)

    context.abort.assert_not_awaited()
