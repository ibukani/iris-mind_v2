"""FakeLLMClientの決定論的動作のテスト。"""

from __future__ import annotations

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.ports import LLMMessage, LLMRequest, LLMResponse, LLMRole


@pytest.mark.anyio
async def test_fake_llm_returns_deterministic_typed_response() -> None:
    """FakeLLMClientがレスポンスを巡回し、リクエストを記録することを確認する。"""
    client = FakeLLMClient(responses=("first", "second"))
    request = LLMRequest(
        model="fake-llm",
        messages=(LLMMessage(role=LLMRole.USER, content="hello"),),
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
            LLMMessage(role=LLMRole.SYSTEM, content="instruction"),
            LLMMessage(role=LLMRole.USER, content="hello"),
        ),
    )

    response = await client.generate(request)

    assert response == LLMResponse(text="fake response: hello", model="fake-llm")


@pytest.mark.anyio
async def test_fake_llm_extracts_actor_message_from_structured_prompt() -> None:
    """構造化プロンプトからactor messageのみ抽出しレスポンスに含める。"""
    client = FakeLLMClient()
    prompt = (
        "Relevant memories:\n- memory1\n\nPolicy constraints: rule1\n\nActor message:\nこんにちは"
    )
    request = LLMRequest(
        model="fake-llm", messages=(LLMMessage(role=LLMRole.USER, content=prompt),)
    )
    response = await client.generate(request)
    assert response.text == "fake response: こんにちは"


@pytest.mark.anyio
async def test_fake_llm_ignores_sections_after_marker() -> None:
    """Actor message以降の別セクションを無視しmarker直後のテキストのみ抽出する。"""
    client = FakeLLMClient()
    prompt = (
        "Relevant memories:\n- memory1\n\n"
        "Actor message:\nhello\n\n"
        "Extra section:\nshould not appear"
    )
    request = LLMRequest(
        model="fake-llm", messages=(LLMMessage(role=LLMRole.USER, content=prompt),)
    )
    response = await client.generate(request)
    assert "should not appear" not in response.text
    assert response.text == "fake response: hello"


@pytest.mark.anyio
async def test_fake_llm_fallback_when_marker_missing() -> None:
    """Actor message marker がない場合はプロンプト全体が抽出される。"""
    client = FakeLLMClient()
    prompt = "Just a plain text prompt"
    request = LLMRequest(
        model="fake-llm", messages=(LLMMessage(role=LLMRole.USER, content=prompt),)
    )
    response = await client.generate(request)
    assert response.text == "fake response: Just a plain text prompt"
