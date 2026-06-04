"""Constructor-injection-only composition for the default IrisApp.

No service locator, no global registry, no cognitive policy logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.ollama import OllamaConfig, OllamaLLMClient
from iris.adapters.llm.openai import OpenAIConfig, OpenAILLMClient
from iris.runtime.app import IrisApp
from iris.runtime.wiring.cognitive import wire_text_response_cognitive_cycle

if TYPE_CHECKING:
    from iris.adapters.llm.ports import LLMClient


def wire_default_app(llm_client: LLMClient | None = None) -> IrisApp:
    """Wire the default IrisApp with a text-response cognitive cycle.

    Args:
        llm_client: Optional LLM client override.

    Returns:
        A fully wired IrisApp instance.
    """
    cycle = wire_text_response_cognitive_cycle(llm_client)
    return IrisApp(cycle=cycle)


def wire_fake_app(responses: tuple[str, ...] | None = None) -> IrisApp:
    """Wire an IrisApp backed by the fake (deterministic) LLM.

    Args:
        responses: Optional canned responses for the fake LLM.

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
    """Wire an IrisApp backed by the OpenAI LLM client.

    Args:
        config: OpenAI configuration; loaded from env if not provided.
        model: Model name override when config is not provided.

    Returns:
        A fully wired IrisApp instance.
    """
    if config is None:
        config = OpenAIConfig.from_env(model=model)
    return wire_default_app(OpenAILLMClient(config))


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
    return wire_default_app(OllamaLLMClient(config))
