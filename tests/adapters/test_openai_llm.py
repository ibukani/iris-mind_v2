"""responses APIを使用したOpenAILLMClientアダプターのテスト。"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from iris.adapters.llm import openai as openai_adapter
from iris.adapters.llm.openai import OpenAIAdapterError, OpenAIConfig, OpenAILLMClient
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
