"""OpenAIDiagnostics adapter tests."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from iris.adapters.llm import openai_diagnostics
from iris.adapters.llm.diagnostics import (
    LLMProviderDiagnostics,
    ReadinessStatus,
)
from iris.adapters.llm.openai import OpenAIAdapterError, OpenAIConfig
from iris.adapters.llm.openai_diagnostics import OpenAIDiagnostics


@dataclass(frozen=True)
class _ModelEntry:
    """Fake model entry returned by the stubbed /models listing."""

    id: str


@dataclass
class _StubModelsResource:
    """Stub models resource that returns a fixed list of models."""

    entries: list[_ModelEntry] = field(default_factory=list[_ModelEntry])
    error: BaseException | None = None

    async def list(self) -> object:
        """Return the configured entries or raise the configured error."""
        if self.error is not None:
            raise self.error
        return _ModelListing(tuple(self.entries))


class _InvalidShapeModelsResource:
    """Resource that returns an object that does not match the expected shape."""

    async def list(self) -> object:
        return "not a listing"


@dataclass(frozen=True)
class _ModelListing:
    """Container mimicking the openai ``AsyncPage[Model]`` shape."""

    data: tuple[object, ...]


@dataclass
class _StubOpenAIClient:
    """Stub OpenAI client that exposes a fixed models resource."""

    models_resource: _StubModelsResource | _InvalidShapeModelsResource

    @property
    def models(self) -> _StubModelsResource | _InvalidShapeModelsResource:
        """Expose the models resource at the same path as the real client."""
        return self.models_resource


def test_openai_diagnostics_implements_provider_diagnostics_protocol() -> None:
    """OpenAIDiagnostics は provider-neutral Protocol を満たす。"""
    diagnostics = OpenAIDiagnostics(client=_build_stub_client())

    assert isinstance(diagnostics, LLMProviderDiagnostics)
    assert diagnostics.provider == "openai"
    assert diagnostics.capabilities.health_check is True
    assert diagnostics.capabilities.model_availability_check is True
    assert diagnostics.capabilities.model_loaded_check is False
    assert diagnostics.capabilities.warmup is False


@pytest.mark.anyio
async def test_check_readiness_reports_ok_when_model_listed() -> None:
    """Model が /models に含まれる場合は readiness OK を返す。"""
    stub = _StubOpenAIClient(
        models_resource=_StubModelsResource(
            entries=[_ModelEntry(id="gpt-5-mini"), _ModelEntry(id="gpt-5-nano")],
        ),
    )

    result = await OpenAIDiagnostics(client=stub).check_readiness("gpt-5-mini")

    assert result.status is ReadinessStatus.OK
    assert result.issues == ()
    assert result.model == "gpt-5-mini"
    assert result.metadata is not None
    assert result.metadata["available_models"] == "2"


@pytest.mark.anyio
async def test_check_readiness_reports_model_not_available_as_failure() -> None:
    """Model が /models に無い場合は model_not_available を FAIL で報告。"""
    stub = _StubOpenAIClient(
        models_resource=_StubModelsResource(entries=[_ModelEntry(id="other-model")]),
    )

    result = await OpenAIDiagnostics(client=stub).check_readiness("missing-model")

    assert result.status is ReadinessStatus.FAIL
    assert len(result.issues) == 1
    assert result.issues[0].code == "model_not_available"


@pytest.mark.anyio
async def test_check_readiness_reports_authentication_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API key 認証エラーは authentication_failed を FAIL で報告。"""
    _patch_api_error(monkeypatch)
    stub = _StubOpenAIClient(
        models_resource=_StubModelsResource(
            error=_FakeAPIError("Unauthorized: invalid API key"),
        ),
    )

    result = await OpenAIDiagnostics(client=stub).check_readiness("gpt-5-mini")

    assert result.status is ReadinessStatus.FAIL
    assert result.issues[0].code == "authentication_failed"


@pytest.mark.anyio
async def test_check_readiness_reports_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rate limit エラーは rate_limited を FAIL で報告。"""
    _patch_api_error(monkeypatch)
    stub = _StubOpenAIClient(
        models_resource=_StubModelsResource(
            error=_FakeAPIError("Rate limit reached (HTTP 429)"),
        ),
    )

    result = await OpenAIDiagnostics(client=stub).check_readiness("gpt-5-mini")

    assert result.status is ReadinessStatus.FAIL
    assert result.issues[0].code == "rate_limited"


@pytest.mark.anyio
async def test_check_readiness_reports_quota_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quota エラーは quota_exceeded を FAIL で報告。"""
    _patch_api_error(monkeypatch)
    stub = _StubOpenAIClient(
        models_resource=_StubModelsResource(
            error=_FakeAPIError("You exceeded your current quota"),
        ),
    )

    result = await OpenAIDiagnostics(client=stub).check_readiness("gpt-5-mini")

    assert result.status is ReadinessStatus.FAIL
    assert result.issues[0].code == "quota_exceeded"


@pytest.mark.anyio
async def test_check_readiness_reports_generic_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未分類エラーは openai_request_failed を FAIL で報告。"""
    _patch_api_error(monkeypatch)
    stub = _StubOpenAIClient(
        models_resource=_StubModelsResource(
            error=_FakeAPIError("network down"),
        ),
    )

    result = await OpenAIDiagnostics(client=stub).check_readiness("gpt-5-mini")

    assert result.status is ReadinessStatus.FAIL
    assert result.issues[0].code == "openai_request_failed"


@pytest.mark.anyio
async def test_check_readiness_reports_invalid_listing_shape() -> None:
    """/models 応答が想定外 shape の場合は openai_list_invalid を FAIL で報告。"""
    stub = _StubOpenAIClient(models_resource=_InvalidShapeModelsResource())

    result = await OpenAIDiagnostics(client=stub).check_readiness("gpt-5-mini")

    assert result.status is ReadinessStatus.FAIL
    assert result.issues[0].code == "openai_list_invalid"


@pytest.mark.anyio
async def test_check_readiness_reports_missing_sdk_as_failure() -> None:
    """openai-SDK 不在時は OpenAIAdapterError を openai_sdk_missing に翻訳。

    注: 先頭小文字の openai は正式名称 (D403) に対する例外として保持。
    """
    stub = _StubOpenAIClient(
        models_resource=_StubModelsResource(
            error=OpenAIAdapterError("OpenAI SDK is not installed"),
        ),
    )

    result = await OpenAIDiagnostics(client=stub).check_readiness("gpt-5-mini")

    assert result.status is ReadinessStatus.FAIL
    assert result.issues[0].code == "openai_sdk_missing"


@pytest.mark.anyio
async def test_warmup_reports_skipped_with_explanation() -> None:
    """OpenAI provider は warmup をサポートしないため SKIPPED を返す。"""
    stub = _build_stub_client()

    result = await OpenAIDiagnostics(client=stub).warmup("gpt-5-mini")

    assert result.status is ReadinessStatus.SKIPPED
    assert len(result.issues) == 1
    assert result.issues[0].code == "warmup_not_supported"


def test_default_construction_raises_when_api_key_missing() -> None:
    """API key も注入 client もない場合 ``OpenAIAdapterError`` を送出。"""
    with pytest.raises(OpenAIAdapterError, match="API key is required"):
        OpenAIDiagnostics(OpenAIConfig(model="gpt-5-mini"))


def _build_stub_client() -> _StubOpenAIClient:
    """Build a default stub client for tests that do not customize the listing.

    Returns:
        A stub client pre-populated with a single ``gpt-5-mini`` model entry.
    """
    return _StubOpenAIClient(
        models_resource=_StubModelsResource(entries=[_ModelEntry(id="gpt-5-mini")]),
    )


def _patch_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the diagnostics module's ``openai_sdk`` reference with a fake module.

    The fake module exposes a single ``APIError`` class used to drive
    the exception-translation path without depending on the openai SDK.

    Args:
        monkeypatch: The pytest monkeypatch fixture.
    """
    fake_module = _FakeOpenAIModule()
    monkeypatch.setattr(openai_diagnostics, "openai_sdk", fake_module)


class _FakeAPIError(Exception):
    """Test double that mimics the openai ``APIError`` shape.

    Used to validate the diagnostics exception-translation path without
    depending on the openai SDK's concrete exception classes.
    """


class _FakeOpenAIModule:
    """Minimal stand-in for the openai SDK module used in tests.

    Exposes an ``APIError`` attribute so the diagnostics ``except`` clause
    can catch it during tests that need to drive error paths.
    """

    APIError = _FakeAPIError
