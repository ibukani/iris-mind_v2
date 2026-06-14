"""Tests for LLM wiring factory functions and edge cases."""

from __future__ import annotations

from typing import Any

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.ollama import OllamaConfig, OllamaLLMClient
from iris.adapters.llm.openai import OpenAIConfig, OpenAILLMClient
from iris.cognitive.action.response import ResponsePrompt
from iris.runtime.config import ConfigError, RuntimeModelConfig, default_runtime_config
from iris.runtime.wiring.llm import (
    LLMClientFactory,
    LLMResponseGenerator,
    ollama_adapter_config,
    openai_adapter_config,
    wire_fake_llm_client,
    wire_ollama_llm_client,
    wire_openai_llm_client,
    wire_response_generator,
)
from tests.helpers.private_access import (
    get_private_attr_as,
    get_private_attr_path_as,
    import_private_matching,
    is_callable,
)


def test_wire_fake_llm_client_returns_fake() -> None:
    """wire_fake_llm_client returns a FakeLLMClient."""
    client = wire_fake_llm_client()
    assert isinstance(client, FakeLLMClient)


def test_wire_fake_llm_client_with_responses() -> None:
    """wire_fake_llm_client passes responses through."""
    client = wire_fake_llm_client(responses=("a", "b"))
    assert get_private_attr_as(client, "_responses", tuple[object, ...]) == ("a", "b")


def test_wire_openai_llm_client_returns_client() -> None:
    """wire_openai_llm_client returns an OpenAILLMClient."""
    config = OpenAIConfig(model="gpt-test", api_key="test-key")
    client = wire_openai_llm_client(config)
    assert isinstance(client, OpenAILLMClient)
    assert get_private_attr_path_as(client, ("_config", "model"), str) == "gpt-test"


def test_wire_ollama_llm_client_returns_client() -> None:
    """wire_ollama_llm_client returns an OllamaLLMClient."""
    config = OllamaConfig(model="qwen3:8b")
    client = wire_ollama_llm_client(config)
    assert isinstance(client, OllamaLLMClient)
    assert get_private_attr_path_as(client, ("_config", "model"), str) == "qwen3:8b"


def test_wire_response_generator_uses_fake_when_client_none() -> None:
    """wire_response_generator creates a fake client when client is None."""
    gen = wire_response_generator(client=None)
    assert isinstance(gen, LLMResponseGenerator)
    assert isinstance(get_private_attr_as(gen, "_client", FakeLLMClient), FakeLLMClient)


def _model_config_with_unknown_provider() -> RuntimeModelConfig:
    """Build a RuntimeModelConfig with an invalid provider value at runtime.

    Returns:
        RuntimeModelConfig with provider set to "unknown".
    """
    # RuntimeModelConfig is frozen and provider is typed as LLMProvider Literal.
    # To test the unknown-provider error path we bypass the dataclass invariant
    # by directly mutating the underlying __dict__ through object.__setattr__.
    model_config = RuntimeModelConfig(provider="fake", model="x")
    model_config.__dict__["provider"] = "unknown"
    return model_config


def test_llm_client_factory_create_client_unknown_provider() -> None:
    """LLMClientFactory.create_client raises ConfigError for unknown provider."""
    factory = LLMClientFactory()
    config = default_runtime_config()
    with pytest.raises(ConfigError, match="Unknown LLM provider"):
        factory.create_client(_model_config_with_unknown_provider(), config)


def test_llm_client_factory_resolve_model_unknown_provider() -> None:
    """LLMClientFactory.resolve_model raises ConfigError for unknown provider."""
    factory = LLMClientFactory()
    config = default_runtime_config()
    with pytest.raises(ConfigError, match="Unknown LLM provider"):
        factory.resolve_model(_model_config_with_unknown_provider(), config)


def test_ollama_adapter_config_replaces_fake_llm_model() -> None:
    """ollama_adapter_config replaces fake-llm with the Ollama default model."""
    config = default_runtime_config()
    model_config = RuntimeModelConfig(provider="ollama", model="fake-llm")
    result = ollama_adapter_config(model_config, config)
    assert result.model == OllamaConfig().model


def test_openai_adapter_config_replaces_fake_llm_model() -> None:
    """openai_adapter_config replaces fake-llm with the OpenAI default model."""
    config = default_runtime_config()
    model_config = RuntimeModelConfig(provider="openai", model="fake-llm")
    result = openai_adapter_config(model_config, config)
    assert result.model == "gpt-5-mini"


def test_openai_adapter_config_uses_runtime_max_tokens() -> None:
    """openai_adapter_config uses runtime max_output_tokens when model config has None."""
    config = default_runtime_config()
    model_config = RuntimeModelConfig(provider="openai", model="gpt-test")
    result = openai_adapter_config(model_config, config)
    assert result.max_output_tokens == config.openai.max_output_tokens


def test_build_user_content_with_no_sections() -> None:
    """_build_user_content returns actor_text when no optional sections are present."""
    build_user_content: Any = import_private_matching(
        "iris.runtime.wiring.llm", "_build_user_content", is_callable
    )
    prompt = ResponsePrompt(
        system_instruction="sys",
        actor_text="hello",
        memory_snippets=(),
        affect_context=None,
        relationship_context=None,
        constraints=(),
        goals=(),
    )
    content = build_user_content(prompt)
    assert content == "hello"


@pytest.mark.anyio
async def test_llm_response_generator_builds_request() -> None:
    """LLMResponseGenerator.builds an LLMRequest and calls the client."""
    client = FakeLLMClient(responses=("reply",), model="test-model")
    gen = LLMResponseGenerator(client, model="test-model")
    prompt = ResponsePrompt(
        system_instruction="You are helpful.",
        actor_text="hi",
    )
    result = await gen.generate_response(prompt)
    assert result.text == "reply"
    assert result.model == "test-model"
