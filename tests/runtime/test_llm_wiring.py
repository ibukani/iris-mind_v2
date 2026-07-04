"""Tests for LLM wiring factory functions and edge cases."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.observability import ObservableLLMClient
from iris.adapters.llm.ollama import OllamaConfig, OllamaLLMClient
from iris.adapters.llm.openai import OpenAIConfig, OpenAILLMClient
from iris.adapters.llm.ports import LLMRole
from iris.contracts.conversation import ConversationRecord, ConversationRole
from iris.core.ids import ObservationId, SessionId
from iris.features.chat.definition import ResponsePrompt
from iris.runtime.config import ConfigError, RuntimeModelConfig, default_runtime_config
from iris.runtime.config.llm import LLMProvider
from iris.runtime.observability.llm import RuntimeLLMRequestObserver
from iris.runtime.observability.ports import RuntimeLatencyBudget
from iris.runtime.prompting.assembler import RuntimePromptAssembler
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
    model_config = RuntimeModelConfig(provider=LLMProvider.FAKE, model="x")
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


def test_llm_client_factory_wraps_client_with_runtime_observer_budget() -> None:
    """Factory が生成 client に runtime latency budget 付き observer を接続する。"""
    factory = LLMClientFactory()
    config = default_runtime_config()
    budget = RuntimeLatencyBudget(llm_generate_ms=12.5)
    config = replace(
        config,
        observability=replace(config.observability, latency_budget=budget),
    )

    client = factory.create_client(
        RuntimeModelConfig(provider=LLMProvider.FAKE, model="fake-llm"), config
    )

    assert isinstance(client, ObservableLLMClient)
    observer = get_private_attr_as(
        client,
        "_observer",
        RuntimeLLMRequestObserver,
    )
    assert get_private_attr_as(observer, "_latency_budget", RuntimeLatencyBudget) == budget


def test_ollama_adapter_config_replaces_fake_llm_model() -> None:
    """ollama_adapter_config replaces fake-llm with the Ollama default model."""
    config = default_runtime_config()
    model_config = RuntimeModelConfig(provider=LLMProvider.OLLAMA, model="fake-llm")
    result = ollama_adapter_config(model_config, config)
    assert result.model == OllamaConfig().model


def test_ollama_adapter_config_passes_runtime_think_false() -> None:
    """ollama_adapter_config passes the default think=False to OllamaConfig."""
    config = default_runtime_config()
    model_config = RuntimeModelConfig(provider=LLMProvider.OLLAMA, model="qwen3.5:9b")
    result = ollama_adapter_config(model_config, config)
    assert result.think is False


def test_ollama_adapter_config_passes_runtime_think_level() -> None:
    """ollama_adapter_config passes a configured think level to OllamaConfig."""
    config = default_runtime_config()
    config = replace(
        config,
        ollama=replace(config.ollama, think="low"),
    )
    model_config = RuntimeModelConfig(provider=LLMProvider.OLLAMA, model="qwen3.5:9b")
    result = ollama_adapter_config(model_config, config)
    assert result.think == "low"


def test_openai_adapter_config_replaces_fake_llm_model() -> None:
    """openai_adapter_config replaces fake-llm with the OpenAI default model."""
    config = default_runtime_config()
    model_config = RuntimeModelConfig(provider=LLMProvider.OPENAI, model="fake-llm")
    result = openai_adapter_config(model_config, config)
    assert result.model == "gpt-5-mini"


def test_openai_adapter_config_uses_runtime_max_tokens() -> None:
    """openai_adapter_config uses runtime max_output_tokens when model config has None."""
    config = default_runtime_config()
    model_config = RuntimeModelConfig(provider=LLMProvider.OPENAI, model="gpt-test")
    result = openai_adapter_config(model_config, config)
    assert result.max_output_tokens == config.openai.max_output_tokens


def test_prompt_assembler_user_message_with_no_sections() -> None:
    """RuntimePromptAssembler keeps actor_text in the final user message."""
    prompt = ResponsePrompt(
        system_instruction="sys",
        actor_text="hello",
        memory_snippets=(),
        affect_context=None,
        relationship_context=None,
        constraints=(),
        goals=(),
    )
    messages = RuntimePromptAssembler().assemble(prompt).messages
    assert messages[-1].role is LLMRole.USER
    assert messages[-1].content == "hello"


def test_prompt_assembler_user_message_excludes_internal_context() -> None:
    """RuntimePromptAssembler keeps internal context out of the final user message."""
    prompt = ResponsePrompt(
        system_instruction="sys",
        actor_text="ありがとう。最後に一言だけ返してください。",
        memory_snippets=("User likes concise replies.",),
        affect_context="neutral VAD(v=0.00, a=0.00, d=0.00)",
        relationship_context="User: neutral relationship, trust=0.50, familiarity=0.00",
        constraints=("keep tone calm", "avoid over-familiarity"),
        goals=("respond_to_user",),
    )

    messages = RuntimePromptAssembler().assemble(prompt).messages
    content = messages[-1].content

    assert content == "ありがとう。最後に一言だけ返してください。"
    assert "Affect context" not in content
    assert "Relationship context" not in content
    assert "Policy constraints" not in content
    assert "trust=0.50" not in content
    assert "familiarity=0.00" not in content
    assert "VAD" not in content


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


@pytest.mark.anyio
async def test_llm_response_generator_includes_prior_conversation_messages() -> None:
    """LLM requestをsystem、過去会話、current userの順で構築する。"""
    client = FakeLLMClient(responses=("reply",), model="test-model")
    prompt = ResponsePrompt(
        system_instruction="You are helpful.",
        actor_text="現在の質問",
        conversation_history=(
            ConversationRecord(
                role=ConversationRole.USER,
                content="前の質問",
                occurred_at=datetime(2026, 6, 30, tzinfo=UTC),
                observation_id=ObservationId("obs-user"),
                session_id=SessionId("session-old"),
            ),
            ConversationRecord(
                role=ConversationRole.ASSISTANT,
                content="前の返答",
                occurred_at=datetime(2026, 6, 30, tzinfo=UTC),
                observation_id=ObservationId("obs-assistant"),
                session_id=SessionId("session-old"),
            ),
        ),
    )
    await LLMResponseGenerator(client, model="test-model").generate_response(prompt)
    request = client.requests[0]
    assert tuple((message.role, message.content) for message in request.messages[1:]) == (
        (LLMRole.USER, "前の質問"),
        (LLMRole.ASSISTANT, "前の返答"),
        (LLMRole.USER, "現在の質問"),
    )
    assert sum(message.content == "現在の質問" for message in request.messages) == 1
    assert "Respond in the same natural language" in request.messages[0].content
    assert "natural Japanese only" in request.messages[0].content
    assert "Do not mix Chinese" in request.messages[0].content


@pytest.mark.anyio
async def test_llm_response_generator_separates_internal_context_from_user_message() -> None:
    """Internal context is system-only; the user message remains clean actor text."""
    client = FakeLLMClient(responses=("reply",), model="test-model")
    gen = LLMResponseGenerator(client, model="test-model")
    actor_text = "ありがとう。最後に一言だけ返してください。"
    prompt = ResponsePrompt(
        system_instruction="Generate a concise text response for Iris.",
        actor_text=actor_text,
        memory_snippets=("User likes concise replies.",),
        affect_context="neutral VAD(v=0.00, a=0.00, d=0.00)",
        relationship_context="User: neutral relationship, trust=0.50, familiarity=0.00",
        constraints=("keep tone calm", "avoid over-familiarity"),
        goals=("respond_to_user",),
    )

    result = await gen.generate_response(prompt)

    assert result.text == "reply"
    assert len(client.requests) == 1
    request = client.requests[0]

    system_messages = [
        message.content for message in request.messages if message.role == LLMRole.SYSTEM
    ]
    user_messages = [
        message.content for message in request.messages if message.role == LLMRole.USER
    ]

    assert len(system_messages) == 1
    assert len(user_messages) == 1

    system_content = system_messages[0]
    user_content = user_messages[0]

    assert user_content == actor_text
    assert "Affect context" not in user_content
    assert "Relationship context" not in user_content
    assert "Policy constraints" not in user_content
    assert "trust=0.50" not in user_content
    assert "familiarity=0.00" not in user_content
    assert "VAD" not in user_content
    assert "response-generation process" not in user_content

    assert "Internal context:" in system_content
    assert "Affect context" in system_content
    assert "Relationship context" in system_content
    assert "Policy constraints" in system_content
    assert "trust=0.50" in system_content
    assert "familiarity=0.00" in system_content
    assert "VAD" in system_content
    assert "Never mention affect scores" in system_content
    assert "response-generation process" in system_content
