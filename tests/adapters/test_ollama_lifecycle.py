"""Ollama request-time lifecycle probe tests."""

from __future__ import annotations

import httpx
import pytest

from iris.adapters.llm.lifecycle import ModelLoadState
from iris.adapters.llm.ollama_lifecycle import OllamaModelLifecycleProbe


@pytest.mark.anyio
async def test_ollama_lifecycle_reports_warm_when_model_loaded() -> None:
    """Loaded model in /api/ps is reported as warm."""
    probe = OllamaModelLifecycleProbe(
        transport=httpx.MockTransport(
            _LifecycleHandler(ps_body=_PS_LOADED, tags_body=_TAGS_WITH_MODEL),
        ),
    )

    snapshot = await probe.snapshot("qwen3:8b")

    assert snapshot.provider == "ollama"
    assert snapshot.model == "qwen3:8b"
    assert snapshot.load_state is ModelLoadState.WARM
    assert snapshot.reason == "model_loaded"
    assert snapshot.latency_ms is not None


@pytest.mark.anyio
async def test_ollama_lifecycle_reports_unloaded_when_installed_not_loaded() -> None:
    """Installed but absent from /api/ps is reported as unloaded."""
    probe = OllamaModelLifecycleProbe(
        transport=httpx.MockTransport(
            _LifecycleHandler(ps_body=_PS_EMPTY, tags_body=_TAGS_WITH_MODEL),
        ),
    )

    snapshot = await probe.snapshot("qwen3:8b")

    assert snapshot.load_state is ModelLoadState.UNLOADED
    assert snapshot.reason == "model_installed_not_loaded"


@pytest.mark.anyio
async def test_ollama_lifecycle_reports_unavailable_when_model_missing() -> None:
    """Model absent from installed tags is unavailable."""
    probe = OllamaModelLifecycleProbe(
        transport=httpx.MockTransport(
            _LifecycleHandler(ps_body=_PS_EMPTY, tags_body=_TAGS_WITHOUT_MODEL),
        ),
    )

    snapshot = await probe.snapshot("qwen3:8b")

    assert snapshot.load_state is ModelLoadState.UNAVAILABLE
    assert snapshot.reason == "model_not_installed"


@pytest.mark.anyio
async def test_ollama_lifecycle_reports_unknown_when_loaded_state_unreadable() -> None:
    """Installed model is not marked unloaded when /api/ps is inconclusive."""
    probe = OllamaModelLifecycleProbe(
        transport=httpx.MockTransport(
            _LifecycleHandler(ps_body={"unexpected": []}, tags_body=_TAGS_WITH_MODEL),
        ),
    )

    snapshot = await probe.snapshot("qwen3:8b")

    assert snapshot.load_state is ModelLoadState.UNKNOWN
    assert snapshot.reason == "/api/ps_invalid_response"


@pytest.mark.anyio
async def test_ollama_lifecycle_reports_unavailable_on_connection_error() -> None:
    """Connection failures are unavailable so generation can fail fast."""
    probe = OllamaModelLifecycleProbe(transport=httpx.MockTransport(_connect_error))

    snapshot = await probe.snapshot("qwen3:8b")

    assert snapshot.load_state is ModelLoadState.UNAVAILABLE
    assert snapshot.reason == "daemon_unreachable"


@pytest.mark.anyio
async def test_ollama_lifecycle_reports_unavailable_on_timeout() -> None:
    """Timeouts are unavailable so generation can fail fast."""
    probe = OllamaModelLifecycleProbe(transport=httpx.MockTransport(_timeout_error))

    snapshot = await probe.snapshot("qwen3:8b")

    assert snapshot.load_state is ModelLoadState.UNAVAILABLE
    assert snapshot.reason == "lifecycle_probe_timeout"


@pytest.mark.anyio
async def test_ollama_lifecycle_reports_unknown_on_generic_http_error() -> None:
    """Repeated generic HTTP errors preserve the last inconclusive endpoint reason."""
    probe = OllamaModelLifecycleProbe(transport=httpx.MockTransport(_read_error))

    snapshot = await probe.snapshot("qwen3:8b")

    assert snapshot.load_state is ModelLoadState.UNKNOWN
    assert snapshot.reason == "/api/tags_request_failed"


@pytest.mark.anyio
async def test_ollama_lifecycle_reports_unknown_on_invalid_tags() -> None:
    """Invalid tags response is inconclusive, not model-unavailable."""
    probe = OllamaModelLifecycleProbe(
        transport=httpx.MockTransport(
            _LifecycleHandler(ps_body=_PS_EMPTY, tags_body={"unexpected": []}),
        ),
    )

    snapshot = await probe.snapshot("qwen3:8b")

    assert snapshot.load_state is ModelLoadState.UNKNOWN
    assert snapshot.reason == "/api/tags_invalid_response"


@pytest.mark.anyio
async def test_ollama_lifecycle_reports_unknown_on_ps_http_error() -> None:
    """HTTP errors from /api/ps are inconclusive when tags prove install."""
    probe = OllamaModelLifecycleProbe(
        transport=httpx.MockTransport(
            _ResponseHandler(
                ps_response=httpx.Response(500, request=_request("/api/ps")),
                tags_response=httpx.Response(200, json=_TAGS_WITH_MODEL, request=_request("/api/tags")),
            ),
        ),
    )

    snapshot = await probe.snapshot("qwen3:8b")

    assert snapshot.load_state is ModelLoadState.UNKNOWN
    assert snapshot.reason == "/api/ps_http_500"


@pytest.mark.anyio
async def test_ollama_lifecycle_reports_unknown_on_tags_http_error() -> None:
    """HTTP errors from /api/tags are inconclusive when model is not loaded."""
    probe = OllamaModelLifecycleProbe(
        transport=httpx.MockTransport(
            _ResponseHandler(
                ps_response=httpx.Response(200, json=_PS_EMPTY, request=_request("/api/ps")),
                tags_response=httpx.Response(503, request=_request("/api/tags")),
            ),
        ),
    )

    snapshot = await probe.snapshot("qwen3:8b")

    assert snapshot.load_state is ModelLoadState.UNKNOWN
    assert snapshot.reason == "/api/tags_http_503"


@pytest.mark.anyio
async def test_ollama_lifecycle_reports_unknown_on_invalid_json() -> None:
    """Malformed JSON from /api/ps is inconclusive."""
    probe = OllamaModelLifecycleProbe(
        transport=httpx.MockTransport(
            _ResponseHandler(
                ps_response=httpx.Response(200, content=b"not-json", request=_request("/api/ps")),
                tags_response=httpx.Response(200, json=_TAGS_WITH_MODEL, request=_request("/api/tags")),
            ),
        ),
    )

    snapshot = await probe.snapshot("qwen3:8b")

    assert snapshot.load_state is ModelLoadState.UNKNOWN
    assert snapshot.reason == "/api/ps_invalid_response"


_PS_LOADED: dict[str, object] = {"models": [{"name": "qwen3:8b", "size": 4_000_000_000}]}
_PS_EMPTY: dict[str, object] = {"models": []}
_TAGS_WITH_MODEL: dict[str, object] = {"models": [{"name": "qwen3:8b"}, {"name": "llama3:8b"}]}
_TAGS_WITHOUT_MODEL: dict[str, object] = {"models": [{"name": "llama3:8b"}]}


def _request(path: str) -> httpx.Request:
    """Build a request object for a fixed mock endpoint."""
    return httpx.Request("GET", f"http://testserver{path}")


def _connect_error(request: httpx.Request) -> httpx.Response:
    message = "connection refused"
    raise httpx.ConnectError(message, request=request)


def _timeout_error(request: httpx.Request) -> httpx.Response:
    message = "probe timeout"
    raise httpx.TimeoutException(message, request=request)


def _read_error(request: httpx.Request) -> httpx.Response:
    message = "read failed"
    raise httpx.ReadError(message, request=request)


class _LifecycleHandler:
    """HTTPX mock handler for Ollama lifecycle endpoints."""

    def __init__(self, *, ps_body: dict[str, object], tags_body: dict[str, object]) -> None:
        """Create handler with fixed /api/ps and /api/tags bodies."""
        self._ps_body = ps_body
        self._tags_body = tags_body

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Return a mock response for the requested Ollama endpoint."""
        if request.url.path == "/api/ps":
            return httpx.Response(200, json=self._ps_body, request=request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=self._tags_body, request=request)
        return httpx.Response(404, request=request)


class _ResponseHandler:
    """HTTPX mock handler using prebuilt responses."""

    def __init__(self, *, ps_response: httpx.Response, tags_response: httpx.Response) -> None:
        """Create handler with fixed responses."""
        self._ps_response = ps_response
        self._tags_response = tags_response

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Return the configured response for the requested endpoint."""
        if request.url.path == "/api/ps":
            return self._ps_response
        if request.url.path == "/api/tags":
            return self._tags_response
        return httpx.Response(404, request=request)
