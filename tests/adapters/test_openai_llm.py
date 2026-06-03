from __future__ import annotations

from dataclasses import dataclass

import pytest

from iris.adapters.llm import openai as openai_adapter
from iris.adapters.llm.openai import OpenAIAdapterError, OpenAIConfig, OpenAILLMClient
from iris.adapters.llm.ports import LLMMessage, LLMRequest, LLMResponse


class StubResponsesResource:
    def __init__(self, response: object) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.requests.append(kwargs)
        return self.response


class StubOpenAIClient:
    def __init__(self, response: object) -> None:
        self.responses = StubResponsesResource(response)


@dataclass(frozen=True)
class StubOutputTextResponse:
    output_text: str
    model: str
    status: str


def test_openai_config_can_be_constructed_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    config = OpenAIConfig.from_env(model="gpt-test")

    assert config == OpenAIConfig(model="gpt-test")


@pytest.mark.anyio
async def test_openai_client_converts_llm_request_to_responses_api_shape() -> None:
    stub_client = StubOpenAIClient(StubOutputTextResponse("reply", "gpt-test", "completed"))
    client = OpenAILLMClient(OpenAIConfig(model="gpt-test", max_output_tokens=128), client=stub_client)
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
    stub_client = StubOpenAIClient(StubOutputTextResponse("provider text", "gpt-provider", "completed"))
    client = OpenAILLMClient(OpenAIConfig(model="gpt-test"), client=stub_client)

    response = await client.generate(LLMRequest(model="gpt-test", messages=()))

    assert response == LLMResponse(text="provider text", model="gpt-provider", finish_reason="completed")


@pytest.mark.anyio
async def test_openai_client_extracts_text_from_structured_response() -> None:
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
    client = OpenAILLMClient(OpenAIConfig(model="gpt-test"), client=StubOpenAIClient(provider_response))

    response = await client.generate(LLMRequest(model="gpt-test", messages=()))

    assert response == LLMResponse(text="first second", model="gpt-test")


def test_openai_client_import_is_safe_when_sdk_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openai_adapter, "_openai", None)

    with pytest.raises(OpenAIAdapterError, match="OpenAI SDK is not installed"):
        OpenAILLMClient(OpenAIConfig(model="gpt-test", api_key="test-key"))


def test_openai_client_requires_api_key_only_without_injected_client() -> None:
    OpenAILLMClient(OpenAIConfig(model="gpt-test"), client=StubOpenAIClient(StubOutputTextResponse("", "", "")))

    with pytest.raises(OpenAIAdapterError, match="API key is required"):
        OpenAILLMClient(OpenAIConfig(model="gpt-test"))
