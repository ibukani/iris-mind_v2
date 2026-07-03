"""Ollama diagnostics coverage regression tests."""

from __future__ import annotations

import json
from typing import TypeGuard

import httpx
import pytest

from iris.adapters.llm.diagnostics import ReadinessStatus
from iris.adapters.llm.ollama import OllamaConfig
from iris.adapters.llm.ollama_diagnostics import OllamaDiagnostics
from tests.helpers.approx import approx

_TAGS_BODY: dict[str, object] = {"models": [{"name": "qwen3:8b"}]}
_PS_LOADED: dict[str, object] = {"models": [{"name": "qwen3:8b"}]}


@pytest.mark.anyio
async def test_warmup_connect_error_is_translated_to_failure() -> None:
    """Warmup connection errors are translated into FAIL diagnostics."""
    transport = httpx.MockTransport(_WarmupErrorHandler("connect"))

    result = await OllamaDiagnostics(transport=transport).warmup("qwen3:8b")

    assert result.status is ReadinessStatus.FAIL
    assert result.issues[0].code == "warmup_failed"
    assert "could not connect" in result.issues[0].message


@pytest.mark.anyio
async def test_warmup_timeout_error_is_translated_to_failure() -> None:
    """Warmup timeout errors are translated into FAIL diagnostics."""
    transport = httpx.MockTransport(_WarmupErrorHandler("timeout"))

    result = await OllamaDiagnostics(transport=transport).warmup("qwen3:8b")

    assert result.status is ReadinessStatus.FAIL
    assert result.issues[0].code == "warmup_failed"
    assert "timed out" in result.issues[0].message


@pytest.mark.anyio
async def test_warmup_generic_http_error_is_translated_to_failure() -> None:
    """Warmup generic HTTP errors are translated into FAIL diagnostics."""
    transport = httpx.MockTransport(_WarmupErrorHandler("read"))

    result = await OllamaDiagnostics(transport=transport).warmup("qwen3:8b")

    assert result.status is ReadinessStatus.FAIL
    assert result.issues[0].code == "warmup_failed"
    assert "warmup failed" in result.issues[0].message


@pytest.mark.anyio
async def test_warmup_payload_includes_keep_alive_and_num_predict() -> None:
    """Warmup payload preserves keep_alive and max output token options."""
    handler = _CapturingWarmupHandler()
    config = OllamaConfig(
        temperature=0.25,
        max_output_tokens=8,
        keep_alive="5m",
    )

    result = await OllamaDiagnostics(
        config,
        transport=httpx.MockTransport(handler),
    ).warmup("qwen3:8b")

    assert result.status is ReadinessStatus.OK
    assert handler.payload is not None
    assert handler.payload["keep_alive"] == "5m"
    options = handler.payload["options"]
    assert _is_dict(options)
    assert options["temperature"] == approx(0.25)
    assert options["num_predict"] == 8


class _WarmupErrorHandler:
    """Mock Ollama handler that fails only the warmup chat request."""

    def __init__(self, mode: str) -> None:
        """Create a handler for the requested error mode."""
        self._mode = mode

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Return Ollama endpoint responses or raise configured chat errors."""
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=_TAGS_BODY, request=request)
        if request.url.path == "/api/chat":
            return self._raise_chat_error(request)
        if request.url.path == "/api/ps":
            return httpx.Response(200, json=_PS_LOADED, request=request)
        return httpx.Response(200, request=request)

    def _raise_chat_error(self, request: httpx.Request) -> httpx.Response:
        """Raise the configured warmup chat error.

        Raises:
            httpx.ConnectError: When configured with ``connect`` mode.
            httpx.TimeoutException: When configured with ``timeout`` mode.
            httpx.ReadError: When configured with ``read`` mode.
        """
        if self._mode == "connect":
            message = "connection refused"
            raise httpx.ConnectError(message, request=request)
        if self._mode == "timeout":
            message = "timeout"
            raise httpx.TimeoutException(message, request=request)
        message = "read failed"
        raise httpx.ReadError(message, request=request)


class _CapturingWarmupHandler:
    """Mock Ollama handler that records the warmup chat payload."""

    def __init__(self) -> None:
        """Initialize the captured payload slot."""
        self.payload: dict[str, object] | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Return mock Ollama responses and capture the chat payload."""
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=_TAGS_BODY, request=request)
        if request.url.path == "/api/chat":
            return self._chat_response(request)
        if request.url.path == "/api/ps":
            return httpx.Response(200, json=_PS_LOADED, request=request)
        return httpx.Response(200, request=request)

    def _chat_response(self, request: httpx.Request) -> httpx.Response:
        """Capture and acknowledge the warmup chat request.

        Returns:
            Successful mock ``/api/chat`` response.
        """
        body = json.loads(request.content.decode())
        assert _is_dict(body)
        self.payload = dict(body)
        return httpx.Response(
            200,
            json={"message": {"content": ""}, "model": body.get("model", "")},
            request=request,
        )


def _is_dict(value: object) -> TypeGuard[dict[str, object]]:
    """Narrow a JSON-like value to a dictionary.

    Returns:
        True when ``value`` is a dictionary.
    """
    return isinstance(value, dict)
