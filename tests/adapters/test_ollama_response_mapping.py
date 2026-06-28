"""Regression tests for Ollama response mapping."""

from __future__ import annotations

from typing import Any

import pytest

from iris.adapters.llm.diagnostics import LLMProviderInvalidResponseError
from tests.helpers.private_access import import_private_matching, is_callable


def test_ollama_response_prefers_content_over_thinking() -> None:
    """Ollama response mapping uses message.content, never message.thinking."""
    to_llm_response: Any = import_private_matching(
        "iris.adapters.llm.ollama",
        "_to_llm_response",
        is_callable,
    )
    body = {
        "model": "qwen3.5:9b",
        "message": {
            "role": "assistant",
            "content": "public response",
            "thinking": "private reasoning must not be used",
        },
        "done": True,
        "done_reason": "stop",
    }

    result = to_llm_response(body, fallback_model="fallback-model")

    assert result.text == "public response"
    assert result.model == "qwen3.5:9b"
    assert result.finish_reason == "stop"


def test_ollama_response_does_not_fallback_to_thinking() -> None:
    """Blank content with thinking must be treated as invalid, not leaked."""
    to_llm_response: Any = import_private_matching(
        "iris.adapters.llm.ollama",
        "_to_llm_response",
        is_callable,
    )
    body = {
        "model": "qwen3.5:9b",
        "message": {
            "role": "assistant",
            "content": "",
            "thinking": "private reasoning must not leak",
        },
        "done": True,
        "done_reason": "stop",
    }

    with pytest.raises(
        LLMProviderInvalidResponseError,
        match="missing message content",
    ):
        to_llm_response(body, fallback_model="fallback-model")


def test_ollama_response_missing_content_does_not_use_thinking() -> None:
    """Missing content with thinking must also be invalid."""
    to_llm_response: Any = import_private_matching(
        "iris.adapters.llm.ollama",
        "_to_llm_response",
        is_callable,
    )
    body = {
        "model": "qwen3.5:9b",
        "message": {
            "role": "assistant",
            "thinking": "private reasoning must not leak",
        },
        "done": True,
    }

    with pytest.raises(
        LLMProviderInvalidResponseError,
        match="missing message content",
    ):
        to_llm_response(body, fallback_model="fallback-model")
