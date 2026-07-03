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
from iris.contracts.llm import DEFAULT_FAKE_LLM_MODEL, DEFAULT_OLLAMA_MODEL

type _JsonPrimitive = str | int | float | bool | None
type _JsonValue = _JsonPrimitive | _JsonObject | list[_JsonValue]
type _JsonObject = dict[str, _JsonValue]


@dataclass(frozen=True)
class OllamaConfig:
    """Configuration for the local Ollama LLM adapter."""

    model: str = DEFAULT_OLLAMA_MODEL
    base_url: str = "http://localhost:11434"
    timeout_seconds: float = 120.0
    temperature: float = 0.0
    max_output_tokens: int | None = None
    keep_alive: str | None = None
    warmup_prompt: str | None = None
    think: bool | str | None = False


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
        """
        model = self._request_model(request)
        payload = self._build_payload(request, model)
        body = await perform_ollama_request(
            client=self._client,
            base_url=self._config.base_url,
            payload=payload,
            model=model,
        )
        return _to_llm_response(body, fallback_model=model)

    def _request_model(self, request: LLMRequest) -> str:
        if request.model == DEFAULT_FAKE_LLM_MODEL:
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
        if self._config.think is not None:
            payload["think"] = self._config.think
        if self._config.keep_alive is not None:
            payload["keep_alive"] = self._config.keep_alive
        return payload


async def perform_ollama_request(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    payload: _JsonObject,
    model: str,
) -> _JsonObject:
    """POST the chat payload to Ollama and return the decoded JSON body.

    Args:
        client: The httpx client used to issue the request.
        base_url: Base URL of the Ollama host, used in connection error messages.
        payload: JSON body that will be sent to ``/api/chat``.
        model: The model name that was requested (used for error messages).

    Returns:
        Decoded JSON body of the Ollama response.

    Raises:
        LLMProviderTimeoutError: If the Ollama request times out.
        LLMProviderConnectionError: If the Ollama endpoint is unreachable.
        LLMProviderError: For any other transport-level failure.
    """
    try:
        response = await client.post("/api/chat", json=payload)
    except httpx.TimeoutException as exc:
        message = f"Ollama request timed out for model {model!r}"
        raise LLMProviderTimeoutError(message) from exc
    except httpx.ConnectError as exc:
        message = f"Ollama is unreachable at {base_url}"
        raise LLMProviderConnectionError(message) from exc
    except httpx.HTTPError as exc:
        message = f"Ollama request failed: {exc}"
        raise LLMProviderError(message) from exc
    return _decode_ollama_response(response, model=model)


def _decode_ollama_response(response: httpx.Response, *, model: str) -> _JsonObject:
    """Validate the response status and decode the JSON body.

    Args:
        response: The successful response from the Ollama ``/api/chat`` endpoint.
        model: The model name that was requested (used for error messages).

    Returns:
        Decoded JSON body of the Ollama response.

    Raises:
        LLMProviderModelUnavailableError: If the configured model is unknown.
        LLMProviderAuthenticationError: If the Ollama host rejects credentials.
        LLMProviderRateLimitError: If the Ollama host rate-limits the request.
        LLMProviderInvalidResponseError: If the response shape is invalid.
        LLMProviderError: For any other non-success status code.
    """
    status = response.status_code
    if status == _HTTP_NOT_FOUND:
        message = f"Ollama model {model!r} is unavailable"
        raise LLMProviderModelUnavailableError(message)
    if status in _HTTP_UNAUTHORIZED:
        message = f"Ollama rejected the request with HTTP {status}"
        raise LLMProviderAuthenticationError(message)
    if status == _HTTP_RATE_LIMITED:
        message = f"Ollama rate-limited the request (HTTP {status}) for model {model!r}"
        raise LLMProviderRateLimitError(message)
    if status >= _HTTP_SERVER_ERROR_THRESHOLD:
        message = f"Ollama server error HTTP {status} for model {model!r}"
        raise LLMProviderError(message)
    if status >= _HTTP_OK_THRESHOLD:
        message = f"Ollama returned HTTP {status} for model {model!r}"
        raise LLMProviderError(message)
    try:
        return _decode_json_body(response)
    except LLMProviderInvalidResponseError as exc:
        message = f"Ollama response was not valid JSON: {exc}"
        raise LLMProviderInvalidResponseError(message) from exc


def _decode_json_body(response: httpx.Response) -> _JsonObject:
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
    if not isinstance(content, str) or not content.strip():
        error_message = "Ollama response is missing message content"
        raise LLMProviderInvalidResponseError(error_message)

    provider_model = body.get("model")
    model = provider_model if isinstance(provider_model, str) else fallback_model
    finish_reason = _finish_reason(body)
    return LLMResponse(
        text=content,
        model=model,
        finish_reason=finish_reason,
        load_latency_ms=_duration_ms(body, "load_duration"),
        generation_latency_ms=_duration_ms(body, "eval_duration"),
    )


def _finish_reason(body: _JsonObject) -> str:
    done_reason = body.get("done_reason")
    if isinstance(done_reason, str):
        return done_reason
    return "stop"


def _duration_ms(body: _JsonObject, key: str) -> float | None:
    """Convert an Ollama nanosecond duration field into milliseconds.

    Returns:
        Duration in milliseconds, or ``None`` when the field is absent or invalid.
    """
    value = body.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        if value < 0:
            return None
        return float(value) / 1_000_000.0
    return None


_HTTP_NOT_FOUND = 404
_HTTP_OK_THRESHOLD = 400
_HTTP_UNAUTHORIZED: frozenset[int] = frozenset({401, 403})
_HTTP_RATE_LIMITED = 429
_HTTP_SERVER_ERROR_THRESHOLD = 500
