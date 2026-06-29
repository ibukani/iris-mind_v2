"""OpenAI LLMプロバイダアダプタ。"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import os
from typing import Any, NotRequired, Protocol, TypedDict

from iris.adapters.llm.diagnostics import (
    LLMProviderAuthenticationError,
    LLMProviderConnectionError,
    LLMProviderError,
    LLMProviderModelUnavailableError,
    LLMProviderQuotaError,
    LLMProviderRateLimitError,
    LLMProviderTimeoutError,
)
from iris.adapters.llm.ports import LLMMessage, LLMRequest, LLMResponse
from iris.adapters.llm.type_utils import is_object_mapping, is_object_sequence
from iris.contracts.llm import DEFAULT_FAKE_LLM_MODEL, DEFAULT_OPENAI_MODEL


class OpenAIProviderMessage(TypedDict):
    """OpenAIプロバイダに送信するメッセージの型。"""

    role: str
    content: str


class OpenAIProviderRequestPayload(TypedDict):
    """OpenAIプロバイダに送信するリクエストの型。"""

    model: str
    input: tuple[OpenAIProviderMessage, ...]
    temperature: float
    max_output_tokens: NotRequired[int]


_openai: Any = None
with contextlib.suppress(ImportError):
    import openai as _openai

# Public re-export of the openai SDK module for cross-module use.
# Resolves to ``None`` if the openai SDK is not installed. Sibling
# modules (notably ``openai_diagnostics``) use this public name to
# avoid the ``reportPrivateUsage`` warning that pyright raises on
# underscore-prefixed module attributes.
openai_sdk: Any = _openai


@dataclass(frozen=True)
class OpenAIConfig:
    """OpenAI LLMクライアントの設定。"""

    model: str
    api_key: str | None = None
    timeout_seconds: float | None = None
    max_output_tokens: int | None = None

    @classmethod
    def from_env(
        cls,
        *,
        model: str = DEFAULT_OPENAI_MODEL,
        api_key_name: str = "OPENAI_API_KEY",
        timeout_seconds: float | None = None,
        max_output_tokens: int | None = None,
    ) -> OpenAIConfig:
        """環境変数から設定を生成する。

        Returns:
            OpenAIConfig: 環境変数から生成された設定。
        """
        return cls(
            model=model,
            api_key=os.environ.get(api_key_name),
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
        )


class OpenAIAdapterError(LLMProviderError):
    """OpenAIアダプタ障害時に送出されるエラー。

    :class:`iris.adapters.llm.diagnostics.LLMProviderError` 階層の
    一員として、 gRPC ingress の ``map_exception_to_grpc`` から直接
    ハンドリングできる。 サブクラスでより細かい分類
    (認証 / レート制限 / タイムアウト) を表現する。
    """


class OpenAIResponsesClient(Protocol):
    """OpenAI Responses APIクライアントのプロトコル。"""

    @property
    def responses(self) -> OpenAIResponsesResource:
        """responsesリソースハンドルを返す。"""
        ...


class OpenAIResponsesResource(Protocol):
    """OpenAI Responses APIリソースのプロトコル。"""

    async def create(self, **kwargs: object) -> object:
        """指定されたパラメータで応答を生成する。"""


_ERR_OPENAI_NOT_INSTALLED = "OpenAI SDK is not installed. Install the 'openai' package."
_ERR_API_KEY_REQUIRED = "OpenAI API key is required when no OpenAI client is injected."


class OpenAILLMClient:
    """OpenAI Responses APIをバックエンドとするLLMクライアント。"""

    def __init__(self, config: OpenAIConfig, client: OpenAIResponsesClient | None = None) -> None:
        """設定とオプションの注入クライアントで初期化する。

        Args:
            config: The OpenAI configuration.
            client: An optional injected client instance. When omitted, the client is
                constructed from the config's API key.

        Raises:
            OpenAIAdapterError: openai パッケージがインストールされていない場合。
        """
        self._config = config
        if client is not None:
            self._client = client
            return

        if _openai is None:
            raise OpenAIAdapterError(_ERR_OPENAI_NOT_INSTALLED)
        if config.api_key is None:
            raise OpenAIAdapterError(_ERR_API_KEY_REQUIRED)

        openai_client: OpenAIResponsesClient = _openai.AsyncOpenAI(
            api_key=config.api_key,
            timeout=config.timeout_seconds,
        )
        self._client = openai_client

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """リクエストからLLM応答を生成する。

        Returns:
            LLMResponse: 生成された応答テキストとメタデータ。

        Raises:
            LLMProviderAuthenticationError: API キーが無効 / 権限不足の場合。
            LLMProviderRateLimitError: OpenAI 側でレート制限がかかった場合。
            LLMProviderTimeoutError: SDK がタイムアウト例外を送出した場合。
            LLMProviderConnectionError: 接続失敗 / API エラー時。
            LLMProviderQuotaError: クォータ / 請求上限到達時。
            LLMProviderModelUnavailableError: モデル未発見 / 不正リクエスト時。
        """
        try:
            response = await self._client.responses.create(**self._to_provider_request(request))
        except _TimeoutErrorTypes as exc:
            message = f"OpenAI request timed out: {exc}"
            raise LLMProviderTimeoutError(message) from exc
        except _ConnectionErrorTypes as exc:
            message = f"OpenAI connection failed: {exc}"
            raise LLMProviderConnectionError(message) from exc
        except _AuthenticationErrorTypes as exc:
            message = f"OpenAI authentication failed: {exc}"
            raise LLMProviderAuthenticationError(message) from exc
        except _RateLimitErrorTypes as exc:
            message = f"OpenAI rate limit reached: {exc}"
            raise LLMProviderRateLimitError(message) from exc
        except _QuotaErrorTypes as exc:
            message = f"OpenAI quota exceeded: {exc}"
            raise LLMProviderQuotaError(message) from exc
        except _NotFoundErrorTypes as exc:
            message = f"OpenAI model not found: {exc}"
            raise LLMProviderModelUnavailableError(message) from exc
        except _BadRequestErrorTypes as exc:
            message = f"OpenAI rejected the request: {exc}"
            raise LLMProviderModelUnavailableError(message) from exc
        return LLMResponse(
            text=_extract_output_text(response),
            model=_extract_response_model(response, request.model),
            finish_reason=_extract_finish_reason(response),
        )

    def _request_model(self, request: LLMRequest) -> str:
        if request.model == DEFAULT_FAKE_LLM_MODEL:
            return self._config.model
        return request.model or self._config.model

    def _to_provider_request(self, request: LLMRequest) -> OpenAIProviderRequestPayload:
        max_output_tokens = request.max_tokens or self._config.max_output_tokens
        temperature = request.temperature if request.temperature is not None else 0.0
        provider_request: OpenAIProviderRequestPayload = {
            "model": self._request_model(request),
            "input": tuple(_to_provider_message(message) for message in request.messages),
            "temperature": temperature,
        }
        if max_output_tokens is not None:
            provider_request["max_output_tokens"] = max_output_tokens
        return provider_request


def _to_provider_message(message: LLMMessage) -> OpenAIProviderMessage:
    return {
        "role": message.role,
        "content": message.content,
    }


def _extract_output_text(response: object) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str):
        return output_text

    chunks: list[str] = []
    for output_item in _iter_response_output(response):
        for content_item in _iter_content(output_item):
            text = _get_text(content_item)
            if text:
                chunks.append(text)
    return "".join(chunks)


def _iter_response_output(response: object) -> tuple[object, ...]:
    output = _get_value(response, "output")
    if is_object_sequence(output):
        return tuple(output)
    return ()


def _iter_content(output_item: object) -> tuple[object, ...]:
    content = _get_value(output_item, "content")
    if is_object_sequence(content):
        return tuple(content)
    return ()


def _get_text(content_item: object) -> str | None:
    text = _get_value(content_item, "text")
    if isinstance(text, str):
        return text
    return None


def _get_value(item: object, name: str) -> object:
    if is_object_mapping(item):
        for key, value in item.items():
            if key == name:
                return value
        return None
    return getattr(item, name, None)


def _extract_response_model(response: object, fallback: str) -> str:
    model = getattr(response, "model", None)
    if isinstance(model, str):
        return model
    return fallback


def _extract_finish_reason(response: object) -> str:
    status = getattr(response, "status", None)
    if isinstance(status, str):
        return status
    return "stop"


class _UnreachableSentinel(BaseException):
    """Sentinel exception used to make ``except`` clauses valid but inert.

    The class is intentionally a :class:`BaseException` subclass so it
    is structurally compatible with the exception-type tuples the
    ``except`` clauses expect. It is **never raised by the SDK nor the
    adapter**, so empty SDK-error buckets still produce a working
    ``except`` clause that simply never matches real exceptions.

    Using this sentinel instead of ``Exception`` prevents a missing
    SDK exception from silently widening the catch to all exceptions,
    which would misclassify unrelated provider errors.
    """


_SDK_ERROR_TYPE_NAMES: tuple[str, ...] = (
    "APITimeoutError",
    "Timeout",
    "APIConnectionError",
    "APIError",
    "AuthenticationError",
    "PermissionDeniedError",
    "RateLimitError",
    "NotFoundError",
    "BadRequestError",
)


def _resolve_sdk_error_types() -> tuple[type[BaseException], ...]:
    """Resolve the SDK-specific exception classes the adapter should translate.

    Returns:
        A tuple of exception classes the adapter translates into
        :class:`LLMProviderError` subclasses. When the openai SDK is
        not installed, the returned tuple is empty.
    """
    if _openai is None:
        return ()
    candidates: list[type[BaseException]] = []
    for name in _SDK_ERROR_TYPE_NAMES:
        cls = getattr(_openai, name, None)
        if isinstance(cls, type) and issubclass(cls, BaseException):
            candidates.append(cls)
    return tuple(candidates)


_SDK_ERROR_TYPES: tuple[type[BaseException], ...] = _resolve_sdk_error_types()
_TIMEOUT_ERROR_TYPES: tuple[type[BaseException], ...] = tuple(
    cls for cls in _SDK_ERROR_TYPES if cls.__name__ in {"APITimeoutError", "Timeout"}
)
_AUTH_ERROR_TYPES: tuple[type[BaseException], ...] = tuple(
    cls
    for cls in _SDK_ERROR_TYPES
    if cls.__name__ in {"AuthenticationError", "PermissionDeniedError"}
)
_RATE_LIMIT_ERROR_TYPES: tuple[type[BaseException], ...] = tuple(
    cls for cls in _SDK_ERROR_TYPES if cls.__name__ == "RateLimitError"
)
# ``APIConnectionError`` only — ``APIError`` is the base of all status
# errors and would otherwise over-catch rate-limit / auth / not-found
# and misclassify them as connection failures.
_CONNECTION_ERROR_TYPES: tuple[type[BaseException], ...] = tuple(
    cls for cls in _SDK_ERROR_TYPES if cls.__name__ == "APIConnectionError"
)
_NOT_FOUND_ERROR_TYPES: tuple[type[BaseException], ...] = tuple(
    cls for cls in _SDK_ERROR_TYPES if cls.__name__ == "NotFoundError"
)
_BAD_REQUEST_ERROR_TYPES: tuple[type[BaseException], ...] = tuple(
    cls for cls in _SDK_ERROR_TYPES if cls.__name__ == "BadRequestError"
)
# Quota / billing errors are not part of the openai SDK's exception
# hierarchy; keep the bucket defined so future SDK versions can wire
# it up without changing the call site.
_QUOTA_ERROR_TYPES: tuple[type[BaseException], ...] = tuple(
    cls
    for cls in _SDK_ERROR_TYPES
    if cls.__name__ in {"QuotaExceededError", "InsufficientQuotaError"}
)


def _sentinel_bucket(
    classes: tuple[type[BaseException], ...],
) -> tuple[type[BaseException], ...]:
    """Return ``classes`` if non-empty, otherwise a single-element tuple of the sentinel.

    Args:
        classes: The resolved SDK exception classes for the bucket.

    Returns:
        ``classes`` when at least one SDK class is available, otherwise
        a single-element tuple containing :class:`_UnreachableSentinel`
        so the resulting ``except`` clause is valid but never matches a
        real exception.
    """
    if classes:
        return classes
    return (_UnreachableSentinel,)


# Fallback aliases keep the except clauses syntactically valid when the
# SDK is missing. They use ``_UnreachableSentinel`` instead of
# ``Exception`` so the catch is structurally a no-op rather than a
# broad over-catch.
_TimeoutErrorTypes: tuple[type[BaseException], ...] = _sentinel_bucket(_TIMEOUT_ERROR_TYPES)
_AuthenticationErrorTypes: tuple[type[BaseException], ...] = _sentinel_bucket(_AUTH_ERROR_TYPES)
_RateLimitErrorTypes: tuple[type[BaseException], ...] = _sentinel_bucket(_RATE_LIMIT_ERROR_TYPES)
_ConnectionErrorTypes: tuple[type[BaseException], ...] = _sentinel_bucket(_CONNECTION_ERROR_TYPES)
_NotFoundErrorTypes: tuple[type[BaseException], ...] = _sentinel_bucket(_NOT_FOUND_ERROR_TYPES)
_BadRequestErrorTypes: tuple[type[BaseException], ...] = _sentinel_bucket(_BAD_REQUEST_ERROR_TYPES)
_QuotaErrorTypes: tuple[type[BaseException], ...] = _sentinel_bucket(_QUOTA_ERROR_TYPES)
