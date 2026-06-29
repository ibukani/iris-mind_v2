"""provider例外からgRPC statusへの変換。"""

from __future__ import annotations

import grpc

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

_PROVIDER_ERROR_TO_STATUS: tuple[tuple[type[LLMProviderError], grpc.StatusCode], ...] = (
    (LLMProviderAuthenticationError, grpc.StatusCode.UNAUTHENTICATED),
    (LLMProviderConnectionError, grpc.StatusCode.UNAVAILABLE),
    (LLMProviderTimeoutError, grpc.StatusCode.DEADLINE_EXCEEDED),
    (LLMProviderRateLimitError, grpc.StatusCode.RESOURCE_EXHAUSTED),
    (LLMProviderQuotaError, grpc.StatusCode.RESOURCE_EXHAUSTED),
    (LLMProviderModelUnavailableError, grpc.StatusCode.FAILED_PRECONDITION),
    (LLMProviderInvalidResponseError, grpc.StatusCode.INTERNAL),
)


def map_provider_error_to_status(exc: LLMProviderError) -> grpc.StatusCode:
    """provider例外を最も具体的なgRPC statusへ変換する。

    Returns:
        対応するgRPC status。
    """
    for error_type, status in _PROVIDER_ERROR_TO_STATUS:
        if isinstance(exc, error_type):
            return status
    return grpc.StatusCode.UNKNOWN


def map_exception_to_grpc(exc: BaseException) -> tuple[grpc.StatusCode, str]:
    """例外をclient向けgRPC statusとmessageへ変換する。

    Returns:
        gRPC statusと安全なmessage。
    """
    if isinstance(exc, LLMProviderError):
        status = map_provider_error_to_status(exc)
        return status, f"provider error: {exc}"
    return grpc.StatusCode.INTERNAL, "runtime service failed"
