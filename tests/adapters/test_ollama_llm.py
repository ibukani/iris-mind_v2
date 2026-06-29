"""OllamaLLMClient adapter tests."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import TypeGuard

import httpx
import pytest

from iris.adapters.llm.diagnostics import (
    LLMProviderAuthenticationError,
    LLMProviderConnectionError,
    LLMProviderError,
    LLMProviderInvalidResponseError,
    LLMProviderModelUnavailableError,
    LLMProviderRateLimitError,
    LLMProviderTimeoutError,
)
from iris.adapters.llm.ollama import OllamaConfig, OllamaLLMClient
from iris.adapters.llm.ports import LLMMessage, LLMRequest, LLMResponse, LLMRole

type _JsonPrimitive = str | int | float | bool | None
type _JsonValue = _JsonPrimitive | _JsonObject | list[_JsonValue]
type _JsonObject = dict[str, _JsonValue]


@dataclass
class _RecordedRequest:
    method: str = ""
    path: str = ""
    payload: dict[str, object] | None = None


@pytest.mark.anyio
async def test_ollama_client_posts_chat_payload() -> None:
    """OllamaLLMClient sends a non-streaming /api/chat request."""
    recorded = _RecordedRequest()

    def _handler(request: httpx.Request) -> httpx.Response:
        recorded.method = request.method
        recorded.path = request.url.path
        recorded.payload = _load_json_object(request)
        return httpx.Response(
            200,
            json={"message": {"content": "local text"}, "model": "qwen3:8b"},
            request=request,
        )

    client = OllamaLLMClient(
        OllamaConfig(
            model="qwen3:8b",
            base_url="http://ollama.test",
            temperature=0.25,
            keep_alive="5m",
        ),
        transport=httpx.MockTransport(_handler),
    )

    response = await client.generate(
        LLMRequest(
            model="qwen3:8b",
            messages=(
                LLMMessage(role=LLMRole.SYSTEM, content="system prompt"),
                LLMMessage(role=LLMRole.USER, content="hello"),
            ),
            max_tokens=64,
        )
    )

    assert response == LLMResponse(text="local text", model="qwen3:8b")
    assert recorded.method == "POST"
    assert recorded.path == "/api/chat"
    assert recorded.payload == {
        "model": "qwen3:8b",
        "messages": [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hello"},
        ],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.25, "num_predict": 64},
        "keep_alive": "5m",
    }


@pytest.mark.anyio
async def test_ollama_client_omits_think_when_configured_none() -> None:
    """OllamaLLMClient omits provider thinking flag when configured None."""
    recorded = _RecordedRequest()

    def _handler(request: httpx.Request) -> httpx.Response:
        recorded.payload = _load_json_object(request)
        return httpx.Response(200, json={"message": {"content": "ok"}}, request=request)

    client = OllamaLLMClient(
        OllamaConfig(think=None),
        transport=httpx.MockTransport(_handler),
    )

    await client.generate(LLMRequest(model="qwen3:8b", messages=()))

    assert recorded.payload is not None
    assert "think" not in recorded.payload


@pytest.mark.anyio
async def test_ollama_client_sends_explicit_think_true() -> None:
    """OllamaLLMClient sends provider thinking flag when explicitly enabled."""
    recorded = _RecordedRequest()

    def _handler(request: httpx.Request) -> httpx.Response:
        recorded.payload = _load_json_object(request)
        return httpx.Response(200, json={"message": {"content": "ok"}}, request=request)

    client = OllamaLLMClient(
        OllamaConfig(think=True),
        transport=httpx.MockTransport(_handler),
    )

    await client.generate(LLMRequest(model="qwen3:8b", messages=()))

    assert recorded.payload is not None
    assert recorded.payload["think"] is True


@pytest.mark.anyio
async def test_ollama_client_extracts_response_content_and_model() -> None:
    """OllamaLLMClient extracts text and provider model from the response."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"message": {"content": "provider text"}, "model": "provider-model"},
            request=request,
        )
    )
    client = OllamaLLMClient(OllamaConfig(model="configured-model"), transport=transport)

    response = await client.generate(LLMRequest(model="request-model", messages=()))

    assert response == LLMResponse(text="provider text", model="provider-model")


@pytest.mark.anyio
async def test_ollama_client_falls_back_to_request_model() -> None:
    """OllamaLLMClient uses the request model when the provider omits a model."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"message": {"content": "provider text"}},
            request=request,
        )
    )
    client = OllamaLLMClient(OllamaConfig(model="configured-model"), transport=transport)

    response = await client.generate(LLMRequest(model="request-model", messages=()))

    assert response == LLMResponse(text="provider text", model="request-model")


@pytest.mark.anyio
async def test_ollama_client_falls_back_to_config_model_for_default_request_model() -> None:
    """OllamaLLMClient uses config model when runtime generator leaves the fake default."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"message": {"content": "provider text"}},
            request=request,
        )
    )
    client = OllamaLLMClient(OllamaConfig(model="configured-model"), transport=transport)

    response = await client.generate(LLMRequest(model="fake-llm", messages=()))

    assert response == LLMResponse(text="provider text", model="configured-model")


@pytest.mark.anyio
async def test_ollama_client_uses_config_max_output_tokens() -> None:
    """OllamaLLMClient sends config max_output_tokens when request max_tokens is absent."""
    recorded = _RecordedRequest()

    def _handler(request: httpx.Request) -> httpx.Response:
        recorded.payload = _load_json_object(request)
        return httpx.Response(200, json={"message": {"content": "ok"}}, request=request)

    client = OllamaLLMClient(
        OllamaConfig(model="configured-model", max_output_tokens=32),
        transport=httpx.MockTransport(_handler),
    )

    await client.generate(LLMRequest(model="configured-model", messages=()))

    assert recorded.payload is not None
    options = recorded.payload["options"]
    assert isinstance(options, dict)
    assert options["num_predict"] == 32


@pytest.mark.anyio
async def test_ollama_client_raises_on_non_2xx_response() -> None:
    """OllamaLLMClient wraps non-successful HTTP responses."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(500, json={"error": "failed"}, request=request)
    )
    client = OllamaLLMClient(transport=transport)

    with pytest.raises(LLMProviderError):
        await client.generate(LLMRequest(model="qwen3:8b", messages=()))


@pytest.mark.anyio
async def test_ollama_client_raises_on_invalid_json() -> None:
    """OllamaLLMClient wraps invalid JSON responses."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"{", request=request)
    )
    client = OllamaLLMClient(transport=transport)

    with pytest.raises(LLMProviderInvalidResponseError):
        await client.generate(LLMRequest(model="qwen3:8b", messages=()))


@pytest.mark.anyio
async def test_ollama_client_prefers_content_over_thinking() -> None:
    """OllamaLLMClient never returns provider thinking as response text."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "message": {
                    "content": "provider text",
                    "thinking": "Thinking Process: private reasoning",
                },
            },
            request=request,
        )
    )
    client = OllamaLLMClient(transport=transport)

    response = await client.generate(LLMRequest(model="qwen3:8b", messages=()))

    assert response.text == "provider text"


@pytest.mark.anyio
async def test_ollama_client_uses_thinking_without_content() -> None:
    """OllamaLLMClient treats thinking-only responses as invalid without leaking."""
    thinking = "Thinking Process: private reasoning"
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "message": {
                    "content": "",
                    "thinking": thinking,
                },
            },
            request=request,
        )
    )
    client = OllamaLLMClient(transport=transport)

    with pytest.raises(LLMProviderInvalidResponseError, match="missing message content"):
        await client.generate(LLMRequest(model="qwen3:8b", messages=()))


@pytest.mark.anyio
@pytest.mark.parametrize(
    "provider_body",
    [
        {},
        {"message": {}},
        {"message": {"content": 42}},
    ],
)
async def test_ollama_client_raises_on_invalid_response_shape(
    provider_body: _JsonObject,
) -> None:
    """OllamaLLMClient wraps missing or invalid message content."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=provider_body, request=request)
    )
    client = OllamaLLMClient(transport=transport)

    with pytest.raises(LLMProviderInvalidResponseError):
        await client.generate(LLMRequest(model="qwen3:8b", messages=()))


@pytest.mark.anyio
async def test_ollama_client_raises_on_http_exception() -> None:
    """OllamaLLMClient wraps provider connection exceptions."""

    def _handler(request: httpx.Request) -> httpx.Response:
        message = "connection failed"
        raise httpx.ConnectError(message, request=request)

    client = OllamaLLMClient(transport=httpx.MockTransport(_handler))

    with pytest.raises(LLMProviderConnectionError):
        await client.generate(LLMRequest(model="qwen3:8b", messages=()))


def _load_json_object(request: httpx.Request) -> dict[str, object]:
    payload: object = json.loads(request.content.decode())
    if not _is_dict(payload):
        msg = "request body must be a JSON object"
        raise AssertionError(msg)
    result: dict[str, object] = {}
    for k, v in payload.items():
        assert isinstance(k, str)
        result[k] = v
    return result


def _is_dict(value: object) -> TypeGuard[dict[str, object]]:
    """Narrow object to dict[str, object] for item iteration.

    Runtime check uses isinstance(dict) which erases type parameters, so the
    narrowed type uses the widest compatible parameter types.

    Returns:
        True if value is a dict, narrowing to the widened type.
    """
    return isinstance(value, dict)


# ---------------------------------------------------------------------------
# LLMProviderError translation tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_ollama_client_translates_timeout_to_provider_timeout() -> None:
    """httpx.TimeoutException maps to LLMProviderTimeoutError."""

    def _handler(request: httpx.Request) -> httpx.Response:
        message = "read timeout"
        raise httpx.ReadTimeout(message, request=request)

    client = OllamaLLMClient(transport=httpx.MockTransport(_handler))

    with pytest.raises(LLMProviderTimeoutError):
        await client.generate(LLMRequest(model="qwen3:8b", messages=()))


@pytest.mark.anyio
async def test_ollama_client_translates_connect_error_to_provider_connection() -> None:
    """httpx.ConnectError maps to LLMProviderConnectionError."""

    def _handler(request: httpx.Request) -> httpx.Response:
        message = "connection refused"
        raise httpx.ConnectError(message, request=request)

    client = OllamaLLMClient(transport=httpx.MockTransport(_handler))

    with pytest.raises(LLMProviderConnectionError):
        await client.generate(LLMRequest(model="qwen3:8b", messages=()))


@pytest.mark.anyio
async def test_ollama_client_translates_404_to_model_unavailable() -> None:
    """HTTP 404 maps to LLMProviderModelUnavailableError."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(404, json={"error": "missing"}, request=request)
    )
    client = OllamaLLMClient(transport=transport)

    with pytest.raises(LLMProviderError) as excinfo:
        await client.generate(LLMRequest(model="qwen3:8b", messages=()))

    assert isinstance(excinfo.value, LLMProviderModelUnavailableError)


@pytest.mark.anyio
async def test_ollama_client_translates_401_to_authentication() -> None:
    """HTTP 401 maps to LLMProviderAuthenticationError."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(401, json={"error": "unauthorized"}, request=request)
    )
    client = OllamaLLMClient(transport=transport)

    with pytest.raises(LLMProviderAuthenticationError):
        await client.generate(LLMRequest(model="qwen3:8b", messages=()))


@pytest.mark.anyio
async def test_ollama_client_translates_429_to_rate_limit() -> None:
    """HTTP 429 maps to LLMProviderRateLimitError."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(429, json={"error": "rate"}, request=request)
    )
    client = OllamaLLMClient(transport=transport)

    with pytest.raises(LLMProviderRateLimitError):
        await client.generate(LLMRequest(model="qwen3:8b", messages=()))


@pytest.mark.anyio
async def test_rate_limit_error_message_includes_model() -> None:
    """Rate limit error message includes the requested model name for diagnosis."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(429, json={"error": "rate"}, request=request)
    )
    client = OllamaLLMClient(transport=transport)

    with pytest.raises(LLMProviderRateLimitError) as excinfo:
        await client.generate(LLMRequest(model="qwen3:8b", messages=()))

    assert "qwen3:8b" in str(excinfo.value)


@pytest.mark.anyio
async def test_server_error_message_includes_model() -> None:
    """Server error message includes the requested model name for diagnosis."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(500, json={"error": "boom"}, request=request)
    )
    client = OllamaLLMClient(transport=transport)

    with pytest.raises(LLMProviderError) as excinfo:
        await client.generate(LLMRequest(model="qwen3:8b", messages=()))

    assert "qwen3:8b" in str(excinfo.value)


@pytest.mark.anyio
async def test_ollama_client_translates_invalid_json_to_invalid_response() -> None:
    """Malformed JSON maps to LLMProviderInvalidResponseError."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"{not json", request=request)
    )
    client = OllamaLLMClient(transport=transport)

    with pytest.raises(LLMProviderInvalidResponseError):
        await client.generate(LLMRequest(model="qwen3:8b", messages=()))


@pytest.mark.anyio
async def test_ollama_client_translates_missing_message_to_invalid_response() -> None:
    """Missing ``message`` key maps to LLMProviderInvalidResponseError."""
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}, request=request))
    client = OllamaLLMClient(transport=transport)

    with pytest.raises(LLMProviderInvalidResponseError):
        await client.generate(LLMRequest(model="qwen3:8b", messages=()))


@pytest.mark.anyio
async def test_ollama_client_translates_missing_content_to_invalid_response() -> None:
    """Missing ``message.content`` maps to LLMProviderInvalidResponseError."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"message": {}}, request=request)
    )
    client = OllamaLLMClient(transport=transport)

    with pytest.raises(LLMProviderInvalidResponseError):
        await client.generate(LLMRequest(model="qwen3:8b", messages=()))


@pytest.mark.anyio
async def test_ollama_client_successful_response_unchanged() -> None:
    """A well-formed response still returns an LLMResponse with the expected text."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"message": {"content": "hi"}, "model": "qwen3:8b", "done_reason": "stop"},
            request=request,
        )
    )
    client = OllamaLLMClient(transport=transport)

    response = await client.generate(LLMRequest(model="qwen3:8b", messages=()))

    assert response.text == "hi"
    assert response.model == "qwen3:8b"
    assert response.finish_reason == "stop"
