"""Ollama REST API LLM adapter."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import override

import httpx

from iris.adapters.llm.diagnostics import (
    LLMProviderAuthenticationError,
    LLMProviderConnectionError,
    LLMProviderError,
    LLMProviderInvalidResponseError,
    LLMProviderModelUnavailableError,
    LLMProviderRateLimitError,
    LLMProviderTimeoutError,
)
from iris.adapters.llm.ports import LLMClient, LLMRequest, LLMResponse

type _JsonPrimitive = str | int | float | bool | None
type _JsonValue = _JsonPrimitive | _JsonObject | list[_JsonValue]
type _JsonObject = dict[str, _JsonValue]


@dataclass(frozen=True)
class OllamaConfig:
    """Configuration for the local Ollama LLM adapter."""

    model: str = "qwen3:8b"
    base_url: str = "http://localhost:11434"
    timeout_seconds: float = 120.0
    temperature: float = 0.0
    max_output_tokens: int | None = None
    keep_alive: str | None = None


class OllamaAdapterError(LLMProviderError):
    """Raised when the Ollama adapter cannot produce a valid LLM response.

    ``OllamaAdapterError`` は provider-neutral な
    :class:`iris.adapters.llm.diagnostics.LLMProviderError` 階層の
    一員として gRPC ingress の ``map_exception_to_grpc`` から直接
    ハンドリングできる。 サブクラスでより細かい分類
    (接続失敗 / タイムアウト / 不正レスポンス) を表現する。
    """


class OllamaLLMClient(LLMClient):
    """LLMClient implementation backed by Ollama's local REST API."""

    def __init__(
        self,
        config: OllamaConfig | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create an Ollama LLM client.

        Args:
            config: Adapter-local Ollama configuration.
            client: Optional injected HTTP client for tests or custom transport.
            transport: Optional HTTP transport used when creating the default client.
        """
        self._config = config or OllamaConfig()
        self._client = client or httpx.AsyncClient(
            base_url=self._config.base_url,
            timeout=self._config.timeout_seconds,
            transport=transport,
        )

    @override
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate one non-streaming text response from an LLM request.

        Args:
            request: Provider-neutral LLM request.

        Returns:
            Provider-neutral LLM response.

        Raises:
            LLMProviderConnectionError: If the Ollama endpoint is unreachable.
            LLMProviderTimeoutError: If the Ollama request times out.
            LLMProviderModelUnavailableError: If the configured model is unknown.
                Also raised indirectly by ``_translate_http_status_error``.
            LLMProviderAuthenticationError: If the Ollama host rejects credentials.
                Also raised indirectly by ``_translate_http_status_error``.
            LLMProviderRateLimitError: If the Ollama host rate-limits the request.
                Also raised indirectly by ``_translate_http_status_error``.
            LLMProviderInvalidResponseError: If the response shape is invalid.
            LLMProviderError: For any other provider-side failure.
        """  # noqa: DOC501, DOC502  (helper functions appear as raise targets to ruff)
        model = self._request_model(request)
        payload = self._build_payload(request, model)
        try:
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
            body = _decode_json_response(response)
        except httpx.TimeoutException as exc:
            message = f"Ollama request timed out for model {model!r}"
            raise LLMProviderTimeoutError(message) from exc
        except httpx.ConnectError as exc:
            message = f"Ollama is unreachable at {self._config.base_url}"
            raise LLMProviderConnectionError(message) from exc
        except httpx.HTTPStatusError as exc:
            raise _translate_http_status_error(exc, model) from exc
        except httpx.HTTPError as exc:
            message = f"Ollama request failed: {exc}"
            raise LLMProviderError(message) from exc

        return _to_llm_response(body, fallback_model=model)

    def _request_model(self, request: LLMRequest) -> str:
        if request.model == "fake-llm":
            return self._config.model
        return request.model or self._config.model

    def _build_payload(self, request: LLMRequest, model: str) -> _JsonObject:
        temperature = (
            request.temperature if request.temperature is not None else self._config.temperature
        )
        options: _JsonObject = {"temperature": temperature}
        max_tokens = request.max_tokens or self._config.max_output_tokens
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        payload: _JsonObject = {
            "model": model,
            "messages": [
                {"role": message.role, "content": message.content} for message in request.messages
            ],
            "stream": False,
            "options": options,
        }
        if self._config.keep_alive is not None:
            payload["keep_alive"] = self._config.keep_alive
        return payload


def _decode_json_response(response: httpx.Response) -> _JsonObject:
    try:
        body: _JsonObject = response.json()
    except json.JSONDecodeError as exc:
        message = "Ollama returned invalid JSON"
        raise LLMProviderInvalidResponseError(message) from exc
    return body


def _to_llm_response(body: _JsonObject, *, fallback_model: str) -> LLMResponse:
    message = body.get("message")
    if not isinstance(message, dict):
        error_message = "Ollama response is missing message"
        raise LLMProviderInvalidResponseError(error_message)

    content = message.get("content")
    if not isinstance(content, str):
        error_message = "Ollama response is missing message content"
        raise LLMProviderInvalidResponseError(error_message)

    provider_model = body.get("model")
    model = provider_model if isinstance(provider_model, str) else fallback_model
    finish_reason = _finish_reason(body)
    return LLMResponse(text=content, model=model, finish_reason=finish_reason)


def _finish_reason(body: _JsonObject) -> str:
    done_reason = body.get("done_reason")
    if isinstance(done_reason, str):
        return done_reason
    return "stop"


def _translate_http_status_error(
    exc: httpx.HTTPStatusError,
    model: str,
) -> LLMProviderError:
    """Translate an Ollama HTTP status error into a typed provider error.

    Args:
        exc: The original ``httpx.HTTPStatusError`` raised by the client.
        model: The model name that was requested (for error messages).

    Returns:
        A :class:`LLMProviderError` subclass reflecting the failure
        category.
    """
    status = exc.response.status_code
    if status == _HTTP_NOT_FOUND:
        return LLMProviderModelUnavailableError(f"Ollama model {model!r} is unavailable")
    if status in _HTTP_UNAUTHORIZED:
        return LLMProviderAuthenticationError(f"Ollama rejected the request with HTTP {status}")
    if status >= _HTTP_RATE_LIMITED:
        return _translate_server_or_client_status(status, model)
    return LLMProviderError(f"Ollama returned HTTP {status}")


_HTTP_NOT_FOUND = 404
_HTTP_UNAUTHORIZED: frozenset[int] = frozenset({401, 403})
_HTTP_RATE_LIMITED = 429
_HTTP_SERVER_ERROR_THRESHOLD = 500


def _translate_server_or_client_status(status: int, model: str) -> LLMProviderError:  # noqa: ARG001
    """Translate 4xx/5xx statuses (other than 401/403/404) to a provider error.

    Args:
        status: The HTTP status code returned by Ollama.
        model: The model name that was requested (kept for symmetry).

    Returns:
        A :class:`LLMProviderError` subclass reflecting the failure.
    """
    if status == _HTTP_RATE_LIMITED:
        return LLMProviderRateLimitError(f"Ollama rate-limited the request (HTTP {status})")
    if status >= _HTTP_SERVER_ERROR_THRESHOLD:
        return LLMProviderError(f"Ollama server error HTTP {status}")
    return LLMProviderError(f"Ollama returned HTTP {status}")
