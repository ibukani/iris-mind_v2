"""OllamaDiagnostics adapter tests."""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import TypeGuard

import httpx
import pytest

from iris.adapters.llm.diagnostics import (
    LLMProviderConnectionError,
    LLMProviderDiagnostics,
    LLMProviderError,
    LLMProviderModelUnavailableError,
    LLMProviderTimeoutError,
    ReadinessStatus,
)
from iris.adapters.llm.ollama_diagnostics import OllamaDiagnostics


def test_ollama_diagnostics_implements_provider_diagnostics_protocol() -> None:
    """OllamaDiagnostics は provider-neutral Protocol を満たす。"""
    diagnostics = OllamaDiagnostics()

    assert isinstance(diagnostics, LLMProviderDiagnostics)
    assert diagnostics.provider == "ollama"
    assert diagnostics.capabilities.health_check is True
    assert diagnostics.capabilities.model_availability_check is True
    assert diagnostics.capabilities.model_loaded_check is True
    assert diagnostics.capabilities.warmup is True


@pytest.mark.anyio
async def test_check_readiness_reports_ok_when_daemon_and_model_present() -> None:
    """Ollama daemon と model がいずれも正常なら readiness は OK。"""
    transport = httpx.MockTransport(_build_handler(_TAGS_BODY, _SHOW_BODY))

    result = await OllamaDiagnostics(transport=transport).check_readiness("qwen3:8b")

    assert result.status is ReadinessStatus.OK
    assert result.provider == "ollama"
    assert result.model == "qwen3:8b"
    assert result.issues == ()
    assert result.metadata is not None
    assert result.metadata["installed_models"] == "llama3:8b,qwen3:8b"
    assert result.latency_ms is not None
    assert result.latency_ms >= 0


@pytest.mark.anyio
async def test_check_readiness_reports_daemon_unreachable() -> None:
    """Daemon が到達不能な場合は daemon_unreachable を FAIL で報告。"""
    transport = httpx.MockTransport(_connect_error_handler)

    result = await OllamaDiagnostics(transport=transport).check_readiness("qwen3:8b")

    assert result.status is ReadinessStatus.FAIL
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.code == "daemon_unreachable"
    assert issue.severity is ReadinessStatus.FAIL


@pytest.mark.anyio
async def test_check_readiness_reports_model_not_installed() -> None:
    """タグ一覧に model が無い場合は model_not_installed を FAIL で報告。"""
    transport = httpx.MockTransport(_build_handler(_TAGS_BODY, _SHOW_BODY))

    result = await OllamaDiagnostics(transport=transport).check_readiness("missing-model")

    assert result.status is ReadinessStatus.FAIL
    codes = [issue.code for issue in result.issues]
    assert "model_not_installed" in codes


@pytest.mark.anyio
async def test_check_readiness_reports_show_probe_failure_as_warn() -> None:
    """Model は導入済みだが /api/show が失敗する場合は WARN として報告。"""
    transport = httpx.MockTransport(_build_handler(_TAGS_BODY, error_status=500))

    result = await OllamaDiagnostics(transport=transport).check_readiness("qwen3:8b")

    assert result.status is ReadinessStatus.WARN
    codes = [issue.code for issue in result.issues]
    assert "model_metadata_unavailable" in codes


@pytest.mark.anyio
async def test_check_readiness_reports_tags_endpoint_unavailable() -> None:
    """Tags endpoint が list を返さない場合は WARN として報告。"""
    transport = httpx.MockTransport(_build_handler(_BAD_TAGS_BODY, _SHOW_BODY))

    result = await OllamaDiagnostics(transport=transport).check_readiness("qwen3:8b")

    assert result.status is ReadinessStatus.WARN
    codes = [issue.code for issue in result.issues]
    assert "tags_endpoint_unavailable" in codes


@pytest.mark.anyio
async def test_check_readiness_maps_httpx_timeout_to_provider_error() -> None:
    """Timeout時は ``LLMProviderTimeoutError`` 経由で daemon_unreachable を報告。"""
    transport = httpx.MockTransport(_timeout_error_handler)

    result = await OllamaDiagnostics(transport=transport).check_readiness("qwen3:8b")

    assert result.status is ReadinessStatus.FAIL
    assert result.issues[0].code == "daemon_unreachable"


@pytest.mark.anyio
async def test_warmup_succeeds_when_model_present() -> None:
    """Warmup は generation を 1 件呼んで latency を報告する。"""
    transport = httpx.MockTransport(_build_warmup_handler())

    result = await OllamaDiagnostics(transport=transport).warmup("qwen3:8b")

    assert result.status is ReadinessStatus.OK
    assert result.issues == ()
    assert result.provider == "ollama"
    assert result.model == "qwen3:8b"


@pytest.mark.anyio
async def test_warmup_reports_model_unavailable_as_skipped() -> None:
    """Model 未導入時の warmup は SKIPPED で報告し、欠落モデル名を含む。"""
    transport = httpx.MockTransport(_build_warmup_handler(generation_status=404))

    result = await OllamaDiagnostics(transport=transport).warmup("missing-model")

    assert result.status is ReadinessStatus.SKIPPED
    assert len(result.issues) == 1
    assert result.issues[0].code == "warmup_skipped_model_missing"


@pytest.mark.anyio
async def test_warmup_reports_provider_error_as_failure() -> None:
    """Warmup 時の provider error は FAIL として報告される。"""
    transport = httpx.MockTransport(_build_warmup_handler(generation_status=500))

    result = await OllamaDiagnostics(transport=transport).warmup("qwen3:8b")

    assert result.status is ReadinessStatus.FAIL
    assert result.issues[0].code == "warmup_failed"


_TAGS_BODY: dict[str, object] = {
    "models": [
        {"name": "qwen3:8b", "size": 4_000_000_000},
        {"name": "llama3:8b", "size": 4_000_000_000},
    ],
}
_BAD_TAGS_BODY: dict[str, object] = {"unexpected": "shape"}
_SHOW_BODY: dict[str, object] = {
    "modelfile": "# Modelfile",
    "parameters": 'stop "<|im_end|>"',
    "template": "{{ .Prompt }}",
}


def _build_handler(
    tags_body: dict[str, object],
    show_body: dict[str, object] | None = None,
    *,
    error_status: int | None = None,
) -> _OllamaHandler:
    return _OllamaHandler(
        tags_body=tags_body,
        show_body=show_body or _SHOW_BODY,
        error_status=error_status,
    )


def _build_warmup_handler(*, generation_status: int = 200) -> _OllamaHandler:
    return _OllamaHandler(
        tags_body=_TAGS_BODY,
        show_body=_SHOW_BODY,
        warmup_status=generation_status,
    )


def _connect_error_handler(request: httpx.Request) -> httpx.Response:
    message = "connection refused"
    raise httpx.ConnectError(message, request=request)


def _timeout_error_handler(request: httpx.Request) -> httpx.Response:
    message = "read timeout"
    raise httpx.ReadTimeout(message, request=request)


def _not_found_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(404, request=request)


type _RequestHandler = Callable[[httpx.Request], httpx.Response]


class _OllamaHandler:
    def __init__(
        self,
        *,
        tags_body: dict[str, object],
        show_body: dict[str, object],
        error_status: int | None = None,
        warmup_status: int = 200,
    ) -> None:
        self._tags_body = tags_body
        self._show_body = show_body
        self._error_status = error_status
        self._warmup_status = warmup_status
        self._dispatch: dict[str, _RequestHandler] = {
            "/": self._root_response,
            "/api/tags": self._tags_response,
            "/api/show": self._show_response,
            "/api/chat": self._chat_response,
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        return self._dispatch.get(
            request.url.path,
            _not_found_response,
        )(request)

    def _show_response(self, request: httpx.Request) -> httpx.Response:
        if self._error_status is not None:
            return httpx.Response(self._error_status, request=request)
        return httpx.Response(200, json=self._show_body, request=request)

    def _root_response(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request)

    def _tags_response(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=self._tags_body, request=request)

    def _chat_response(self, request: httpx.Request) -> httpx.Response:
        return self._handle_warmup(request)

    def _handle_warmup(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        if not _is_dict(body):
            msg = "warmup body must be a JSON object"
            raise AssertionError(msg)
        model = body.get("model", "")
        if self._warmup_status == 404:
            return httpx.Response(
                404,
                json={"error": f"model '{model}' not found"},
                request=request,
            )
        if self._warmup_status >= 400:
            return httpx.Response(
                self._warmup_status,
                json={"error": "boom"},
                request=request,
            )
        return httpx.Response(
            200,
            json={"message": {"content": "ok"}, "model": model},
            request=request,
        )


def _is_dict(value: object) -> TypeGuard[dict[str, object]]:
    """Narrow object to dict[str, object] for item iteration.

    Returns:
        True if value is a dict, narrowing to the widened type.
    """
    return isinstance(value, dict)


def test_provider_error_hierarchy_is_exposed() -> None:
    """Provider error classes are importable for the gRPC layer."""
    assert issubclass(LLMProviderConnectionError, LLMProviderError)
    assert issubclass(LLMProviderTimeoutError, LLMProviderError)
    assert issubclass(LLMProviderModelUnavailableError, LLMProviderError)
