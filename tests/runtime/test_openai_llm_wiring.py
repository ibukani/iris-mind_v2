# Copyright 2025 Iris Mind
"""Tests for OpenAI LLM client wiring function."""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.llm.openai import OpenAIConfig, OpenAILLMClient
from iris.runtime.wiring.llm import wire_openai_llm_client

if TYPE_CHECKING:
    from iris.adapters.llm.ports import LLMClient


def test_openai_wiring_returns_llm_client_compatible_instance() -> None:
    """Verify wire_openai_llm_client returns an OpenAILLMClient with generate method."""
    client = wire_openai_llm_client(OpenAIConfig(model="gpt-test", api_key="test-key"))

    assert isinstance(client, OpenAILLMClient)
    assert hasattr(client, "generate")


def test_openai_wiring_return_can_be_typed_as_llm_client() -> None:
    """Verify the return type of wire_openai_llm_client is compatible with LLMClient protocol."""
    client: LLMClient = wire_openai_llm_client(OpenAIConfig(model="gpt-test", api_key="test-key"))

    assert client is not None
