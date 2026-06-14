"""responses APIを使用したOpenAILLMClientアダプターのテスト。"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from iris.adapters.llm import openai as openai_adapter
from iris.adapters.llm.diagnostics import (
    LLMProviderAuthenticationError,
    LLMProviderConnectionError,
    LLMProviderModelUnavailableError,
    LLMProviderQuotaError,
    LLMProviderRateLimitError,
    LLMProviderTimeoutError,
)
from iris.adapters.llm.openai import (
    OpenAIAdapterError,
    OpenAIConfig,
    OpenAILLMClient,
    OpenAIResponsesClient,
)
from iris.adapters.llm.ports import LLMMessage, LLMRequest, LLMResponse


class StubResponsesResource:
    """OpenAI responses APIリソースのスタブ。"""

    def __init__(self, response: object) -> None:
        """固定レスポンスオブジェクトで初期化する。"""
        self.response = response
        self.requests: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        """リクエストを記録してスタブレスポンスを返す。

        Returns:
            object: スタブのレスポンスオブジェクト。
        """
        self.requests.append(kwargs)
        return self.response


class StubOpenAIClient:
    """OpenAIクライアントのスタブ。"""

    def __init__(self, response: object) -> None:
        """スタブresponsesリソースで初期化する。"""
        self.responses = StubResponsesResource(response)


@dataclass(frozen=True)
class StubOutputTextResponse:
    """OpenAI出力テキストレスポンスのスタブ。"""

    output_text: str
    model: str
    status: str


def test_openai_config_can_be_constructed_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """APIキー環境変数が欠落している場合でもOpenAIConfig.from_envが機能することを確認する。"""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    config = OpenAIConfig.from_env(model="gpt-test")

    assert config == OpenAIConfig(model="gpt-test")


@pytest.mark.anyio
async def test_openai_client_converts_llm_request_to_responses_api_shape() -> None:
    """OpenAILLMClientがLLMRequestをOpenAI responses API形式に変換することを確認する。"""
    stub_client = StubOpenAIClient(StubOutputTextResponse("reply", "gpt-test", "completed"))
    client = OpenAILLMClient(
        OpenAIConfig(model="gpt-test", max_output_tokens=128), client=stub_client
    )
    request = LLMRequest(
        model="gpt-test",
        messages=(
            LLMMessage(role="system", content="system text"),
            LLMMessage(role="user", content="user text"),
        ),
        temperature=0.2,
    )

    await client.generate(request)

    assert stub_client.responses.requests == [
        {
            "model": "gpt-test",
            "input": (
                {"role": "system", "content": "system text"},
                {"role": "user", "content": "user text"},
            ),
            "temperature": 0.2,
            "max_output_tokens": 128,
        }
    ]


@pytest.mark.anyio
async def test_openai_client_converts_output_text_response_to_llm_response() -> None:
    """OpenAILLMClientがoutput_textレスポンスをLLMResponseに変換することを確認する。"""
    stub_client = StubOpenAIClient(
        StubOutputTextResponse("provider text", "gpt-provider", "completed")
    )
    client = OpenAILLMClient(OpenAIConfig(model="gpt-test"), client=stub_client)

    response = await client.generate(LLMRequest(model="gpt-test", messages=()))

    assert response == LLMResponse(
        text="provider text", model="gpt-provider", finish_reason="completed"
    )


@pytest.mark.anyio
async def test_openai_client_extracts_text_from_structured_response() -> None:
    """OpenAILLMClientが構造化されたdictレスポンスから連結テキストを抽出することを確認する。"""
    provider_response = {
        "model": "gpt-test",
        "output": [
            {
                "content": [
                    {"text": "first"},
                    {"text": " second"},
                ]
            }
        ],
    }
    client = OpenAILLMClient(
        OpenAIConfig(model="gpt-test"), client=StubOpenAIClient(provider_response)
    )

    response = await client.generate(LLMRequest(model="gpt-test", messages=()))

    assert response == LLMResponse(text="first second", model="gpt-test")


@pytest.mark.anyio
async def test_openai_client_resolves_fake_llm_sentinel_to_config_model() -> None:
    """OpenAILLMClient uses config model when request carries the fake-llm sentinel."""
    stub_client = StubOpenAIClient(StubOutputTextResponse("reply", "gpt-5-mini", "completed"))
    client = OpenAILLMClient(OpenAIConfig(model="gpt-5-mini"), client=stub_client)

    await client.generate(LLMRequest(model="fake-llm", messages=()))

    assert stub_client.responses.requests == [
        {
            "model": "gpt-5-mini",
            "input": (),
            "temperature": 0.0,
        }
    ]


def test_openai_client_import_is_safe_when_sdk_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAI SDKが欠落している場合にOpenAILLMClientがAdapterErrorを発生させることを確認する。"""
    monkeypatch.setattr(openai_adapter, "_openai", None)

    with pytest.raises(OpenAIAdapterError, match="OpenAI SDK is not installed"):
        OpenAILLMClient(OpenAIConfig(model="gpt-test", api_key="test-key"))


def test_openai_client_requires_api_key_only_without_injected_client() -> None:
    """APIキーが欠落している場合にOpenAILLMClientがAdapterErrorを発生させることを確認する。"""
    OpenAILLMClient(
        OpenAIConfig(model="gpt-test"), client=StubOpenAIClient(StubOutputTextResponse("", "", ""))
    )

    with pytest.raises(OpenAIAdapterError, match="API key is required"):
        OpenAILLMClient(OpenAIConfig(model="gpt-test"))


# ---------------------------------------------------------------------------
# LLMProviderError translation tests
# ---------------------------------------------------------------------------


def _make_failing_client(exc: BaseException) -> OpenAIResponsesClient:
    """Build a minimal client stub whose ``responses.create`` raises ``exc``.

    Args:
        exc: The exception to raise on ``create``.

    Returns:
        A stub object exposing ``responses.create`` as an async coroutine.
    """
    class _FailingResource:
        async def create(self, **_kwargs: object) -> object:
            raise exc

    class _FailingClient:
        responses = _FailingResource()

    return _FailingClient()


def _install_exception_types(
    monkeypatch: pytest.MonkeyPatch,
    *,
    timeout: tuple[type[BaseException], ...] = (),
    connection: tuple[type[BaseException], ...] = (),
    auth: tuple[type[BaseException], ...] = (),
) -> None:
    """Patch the openai module's exception-type buckets to include custom classes.

    Args:
        monkeypatch: Pytest fixture used to revert attribute changes.
        timeout: Classes to register as timeout errors.
        connection: Classes to register as connection errors.
        auth: Classes to register as authentication errors.
    """
    monkeypatch.setattr(openai_adapter, "_TimeoutErrorTypes", timeout)
    monkeypatch.setattr(openai_adapter, "_ConnectionErrorTypes", connection)
    monkeypatch.setattr(openai_adapter, "_AuthenticationErrorTypes", auth)


@pytest.mark.anyio
async def test_openai_client_translates_timeout_to_provider_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registered timeout classes map to LLMProviderTimeoutError."""

    class _FakeTimeout(BaseException):
        pass

    _install_exception_types(monkeypatch, timeout=(_FakeTimeout,))

    config = OpenAIConfig(model="gpt-test", api_key="test-key")
    client = OpenAILLMClient(
        config,
        client=_make_failing_client(_FakeTimeout("timed out")),
    )

    with pytest.raises(LLMProviderTimeoutError):
        await client.generate(LLMRequest(model="gpt-test", messages=()))


@pytest.mark.anyio
async def test_openai_client_translates_connection_error_to_provider_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registered connection classes map to LLMProviderConnectionError."""

    class _FakeConnection(BaseException):
        pass

    _install_exception_types(monkeypatch, connection=(_FakeConnection,))

    config = OpenAIConfig(model="gpt-test", api_key="test-key")
    client = OpenAILLMClient(
        config,
        client=_make_failing_client(_FakeConnection("connection failed")),
    )

    with pytest.raises(LLMProviderConnectionError):
        await client.generate(LLMRequest(model="gpt-test", messages=()))


@pytest.mark.anyio
async def test_openai_client_translates_authentication_to_provider_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registered authentication classes map to LLMProviderAuthenticationError."""

    class _FakeAuth(BaseException):
        pass

    _install_exception_types(monkeypatch, auth=(_FakeAuth,))

    config = OpenAIConfig(model="gpt-test", api_key="test-key")
    client = OpenAILLMClient(
        config,
        client=_make_failing_client(_FakeAuth("not allowed")),
    )

    with pytest.raises(LLMProviderAuthenticationError):
        await client.generate(LLMRequest(model="gpt-test", messages=()))


@pytest.mark.anyio
async def test_openai_client_successful_response_unchanged() -> None:
    """A well-formed OpenAI Responses API payload still returns an LLMResponse."""

    class _AttrResponse:
        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    payload = _AttrResponse(output_text="hello", model="gpt-test")
    config = OpenAIConfig(model="gpt-test", api_key="test-key")
    client = OpenAILLMClient(
        config,
        client=StubOpenAIClient(payload),
    )

    response = await client.generate(LLMRequest(model="gpt-test", messages=()))

    assert response.text == "hello"
    assert response.model == "gpt-test"


@pytest.mark.anyio
async def test_openai_client_translates_not_found_to_provider_model_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registered NotFound classes map to LLMProviderModelUnavailableError."""

    class _FakeNotFoundError(Exception):
        pass

    monkeypatch.setattr(openai_adapter, "_NotFoundErrorTypes", (_FakeNotFoundError,))
    monkeypatch.setattr(openai_adapter, "_ConnectionErrorTypes", ())
    monkeypatch.setattr(openai_adapter, "_QuotaErrorTypes", ())
    monkeypatch.setattr(openai_adapter, "_BadRequestErrorTypes", ())
    monkeypatch.setattr(openai_adapter, "_AuthenticationErrorTypes", ())
    monkeypatch.setattr(openai_adapter, "_RateLimitErrorTypes", ())
    monkeypatch.setattr(openai_adapter, "_TimeoutErrorTypes", ())
    client = OpenAILLMClient(
        OpenAIConfig(model="gpt-test", api_key="test-key"),
        client=_make_failing_client(_FakeNotFoundError()),
    )

    with pytest.raises(LLMProviderModelUnavailableError):
        await client.generate(LLMRequest(model="gpt-test", messages=()))


@pytest.mark.anyio
async def test_openai_client_translates_rate_limit_to_provider_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registered RateLimit classes map to LLMProviderRateLimitError."""

    class _FakeRateLimitError(Exception):
        pass

    monkeypatch.setattr(openai_adapter, "_RateLimitErrorTypes", (_FakeRateLimitError,))
    monkeypatch.setattr(openai_adapter, "_ConnectionErrorTypes", ())
    monkeypatch.setattr(openai_adapter, "_QuotaErrorTypes", ())
    monkeypatch.setattr(openai_adapter, "_BadRequestErrorTypes", ())
    monkeypatch.setattr(openai_adapter, "_TimeoutErrorTypes", ())
    client = OpenAILLMClient(
        OpenAIConfig(model="gpt-test", api_key="test-key"),
        client=_make_failing_client(_FakeRateLimitError()),
    )

    with pytest.raises(LLMProviderRateLimitError):
        await client.generate(LLMRequest(model="gpt-test", messages=()))


@pytest.mark.anyio
async def test_openai_client_translates_quota_to_provider_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registered Quota classes map to LLMProviderQuotaError."""

    class _FakeQuotaError(Exception):
        pass

    monkeypatch.setattr(openai_adapter, "_QuotaErrorTypes", (_FakeQuotaError,))
    monkeypatch.setattr(openai_adapter, "_ConnectionErrorTypes", ())
    monkeypatch.setattr(openai_adapter, "_RateLimitErrorTypes", ())
    monkeypatch.setattr(openai_adapter, "_BadRequestErrorTypes", ())
    monkeypatch.setattr(openai_adapter, "_TimeoutErrorTypes", ())
    client = OpenAILLMClient(
        OpenAIConfig(model="gpt-test", api_key="test-key"),
        client=_make_failing_client(_FakeQuotaError()),
    )

    with pytest.raises(LLMProviderQuotaError):
        await client.generate(LLMRequest(model="gpt-test", messages=()))
