"""Ollama REST API LLM adapter."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import override

import httpx

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


class OllamaAdapterError(RuntimeError):
    """Raised when the Ollama adapter cannot produce a valid LLM response."""


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
            OllamaAdapterError: If Ollama cannot return a valid text response.
        """
        model = self._request_model(request)
        payload = self._build_payload(request, model)
        try:
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
            body = _decode_json_response(response)
        except httpx.HTTPStatusError as exc:
            message = f"Ollama returned HTTP {exc.response.status_code}"
            raise OllamaAdapterError(message) from exc
        except httpx.HTTPError as exc:
            message = "Ollama request failed"
            raise OllamaAdapterError(message) from exc

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
        raise OllamaAdapterError(message) from exc
    return body


def _to_llm_response(body: _JsonObject, *, fallback_model: str) -> LLMResponse:
    message = body.get("message")
    if not isinstance(message, dict):
        error_message = "Ollama response is missing message"
        raise OllamaAdapterError(error_message)

    content = message.get("content")
    if not isinstance(content, str):
        error_message = "Ollama response is missing message content"
        raise OllamaAdapterError(error_message)

    provider_model = body.get("model")
    model = provider_model if isinstance(provider_model, str) else fallback_model
    finish_reason = _finish_reason(body)
    return LLMResponse(text=content, model=model, finish_reason=finish_reason)


def _finish_reason(body: _JsonObject) -> str:
    done_reason = body.get("done_reason")
    if isinstance(done_reason, str):
        return done_reason
    return "stop"
