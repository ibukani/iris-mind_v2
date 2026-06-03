"""FakeLLMClientの決定論的動作のテスト。"""

from __future__ import annotations

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.ports import LLMMessage, LLMRequest, LLMResponse


@pytest.mark.anyio
async def test_fake_llm_returns_deterministic_typed_response() -> None:
    """FakeLLMClientがレスポンスを巡回し、リクエストを記録することを確認する。"""
    client = FakeLLMClient(responses=("first", "second"))
    request = LLMRequest(
        model="fake-llm",
        messages=(LLMMessage(role="user", content="hello"),),
    )

    first = await client.generate(request)
    second = await client.generate(request)
    third = await client.generate(request)

    assert first == LLMResponse(text="first", model="fake-llm")
    assert second == LLMResponse(text="second", model="fake-llm")
    assert third == LLMResponse(text="second", model="fake-llm")
    assert client.requests == (request, request, request)


@pytest.mark.anyio
async def test_fake_llm_default_response_uses_last_user_message() -> None:
    """FakeLLMClientがデフォルトで最後のユーザーメッセージをエコーすることを確認する。"""
    client = FakeLLMClient()
    request = LLMRequest(
        model="fake-llm",
        messages=(
            LLMMessage(role="system", content="instruction"),
            LLMMessage(role="user", content="hello"),
        ),
    )

    response = await client.generate(request)

    assert response == LLMResponse(text="fake response: hello", model="fake-llm")
