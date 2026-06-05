"""FakeLLMClientの決定論的動作のテスト。"""

from __future__ import annotations

import pytest

from iris.adapters.llm.fake import (
    FakeLLMClient,
    _actor_text_from_prompt,  # noqa: PLC2701 -- unit-test of internal helper  # pyright: ignore[reportPrivateUsage] -- unit-test of internal helper
)
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


def test_actor_text_from_prompt_extracts_actor_message() -> None:
    """_actor_text_from_prompt が構造化プロンプトから actor message のみを返すことを確認する。"""
    prompt = (
        "Relevant memories:\n- memory1\n\nPolicy constraints: rule1\n\nActor message:\nこんにちは"
    )
    assert _actor_text_from_prompt(prompt) == "こんにちは"


def test_actor_text_from_prompt_ignores_sections_after_marker() -> None:
    """Actor message 以降に別セクションがあっても marker 直後のテキストのみ返すことを確認する。

    将来 _build_user_content が末尾に別セクションを追加した場合の安全策。
    """
    prompt = (
        "Relevant memories:\n- memory1\n\n"
        "Actor message:\nhello\n\n"
        "Extra section:\nshould not appear"
    )
    result = _actor_text_from_prompt(prompt)
    assert "should not appear" not in result
    assert result.strip() == "hello"


def test_actor_text_from_prompt_fallback_when_marker_missing() -> None:
    """Actor message marker がない場合はプロンプト全体を返す。"""
    prompt = "Just a plain text prompt"
    assert _actor_text_from_prompt(prompt) == prompt
