"""Constructor-injection-only composition for the default IrisApp.

No service locator, no global registry, no cognitive policy logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.ollama import OllamaConfig, OllamaLLMClient
from iris.adapters.llm.openai import OpenAIConfig, OpenAILLMClient
from iris.adapters.memory.fake import FakeMemoryStore
from iris.runtime.app import IrisApp
from iris.runtime.wiring.cognitive import (
    wire_policy_affect_memory_aware_text_response_cognitive_cycle,
    wire_text_response_cognitive_cycle,
)
from iris.runtime.wiring.llm import LLMClientFactory

if TYPE_CHECKING:
    from iris.adapters.llm.ports import LLMClient
    from iris.runtime.config import IrisRuntimeConfig


def wire_default_app(
    llm_client: LLMClient,
    *,
    model: str = "fake-llm",
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> IrisApp:
    """Wire an IrisApp using the standard text-response cognitive cycle.

    Args:
        llm_client: LLM client used by response generation.
        model: Model name passed to response generation.
        temperature: Sampling temperature passed to response generation.
        max_tokens: Optional output token limit passed to response generation.

    Returns:
        A fully wired IrisApp instance.
    """
    cycle = wire_text_response_cognitive_cycle(
        llm_client,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return IrisApp(cycle=cycle)


def wire_fake_app(responses: tuple[str, ...] | None = None) -> IrisApp:
    """Wire an IrisApp backed by fake deterministic LLM.

    Args:
        responses: Optional canned response strings for FakeLLMClient.

    Returns:
        A fully wired IrisApp instance.
    """
    llm = FakeLLMClient(responses=responses)
    return wire_default_app(llm)


def wire_openai_app(
    config: OpenAIConfig | None = None,
    *,
    model: str = "gpt-5-mini",
) -> IrisApp:
    """Wire an IrisApp backed by an OpenAI LLM client.

    Args:
        config: OpenAI configuration. When omitted, OPENAI_API_KEY is read from env.
        model: OpenAI model name used when config is not provided.

    Returns:
        A fully wired IrisApp instance.
    """
    if config is None:
        config = OpenAIConfig.from_env(model=model)
    return wire_default_app(OpenAILLMClient(config), model=config.model)


def wire_ollama_app(
    config: OllamaConfig | None = None,
    *,
    model: str = "qwen3:8b",
    base_url: str = "http://localhost:11434",
) -> IrisApp:
    """Wire an IrisApp backed by an Ollama LLM client.

    Args:
        config: Ollama adapter configuration.
        model: Model name used when config is not provided.
        base_url: Ollama host URL used when config is not provided.

    Returns:
        A fully wired IrisApp instance.
    """
    if config is None:
        config = OllamaConfig(model=model, base_url=base_url)
    return wire_default_app(
        OllamaLLMClient(config),
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_output_tokens,
    )


def build_app_from_config(
    config: IrisRuntimeConfig,
    *,
    client_factory: LLMClientFactory | None = None,
) -> IrisApp:
    """Build an IrisApp from runtime configuration.

    The ``default_chat`` model slot is wired into the full cognitive cycle.

    Args:
        config: Runtime configuration.
        client_factory: Optional explicit LLM client factory.

    Returns:
        A fully wired IrisApp instance.
    """
    model_config = config.models.default_chat
    factory = client_factory or LLMClientFactory()
    client = factory.create_client(model_config, config)
    model = factory.resolve_model(model_config, config)
    cycle = wire_policy_affect_memory_aware_text_response_cognitive_cycle(
        memory_store=FakeMemoryStore(),
        llm_client=client,
        model=model,
        temperature=model_config.temperature,
        max_tokens=model_config.max_output_tokens,
    )
    return IrisApp(cycle=cycle)
