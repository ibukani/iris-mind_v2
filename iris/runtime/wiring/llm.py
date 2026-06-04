"""LLM client wiring and response generator implementation."""

from __future__ import annotations

from typing import override

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.ollama import OllamaConfig, OllamaLLMClient
from iris.adapters.llm.openai import OpenAIConfig, OpenAILLMClient
from iris.adapters.llm.ports import LLMClient, LLMMessage, LLMRequest
from iris.cognitive.action.response import GeneratedResponse, ResponseGenerator, ResponsePrompt
from iris.runtime.config import ConfigError, IrisRuntimeConfig, RuntimeModelConfig


class LLMResponseGenerator(ResponseGenerator):
    """ResponseGenerator backed by an LLM client."""

    def __init__(
        self,
        client: LLMClient,
        model: str = "fake-llm",
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> None:
        """Create an LLM-backed response generator.

        Args:
            client: LLM client.
            model: Model name passed to the LLM provider.
            temperature: Sampling temperature passed to the LLM provider.
            max_tokens: Optional output token limit passed to the LLM provider.
        """
        self._client = client
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    @override
    async def generate_response(self, prompt: ResponsePrompt) -> GeneratedResponse:
        """Generate response text for a prompt.

        Args:
            prompt: Response generation prompt.

        Returns:
            Generated response text and model metadata.
        """
        request = LLMRequest(
            model=self._model,
            messages=(
                LLMMessage(role="system", content=prompt.system_instruction),
                LLMMessage(role="user", content=_build_user_content(prompt)),
            ),
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        response = await self._client.generate(request)
        return GeneratedResponse(text=response.text, model=response.model)


def wire_fake_llm_client(responses: tuple[str, ...] | None = None) -> FakeLLMClient:
    """Wire a fake deterministic LLM client.

    Args:
        responses: Optional canned response strings.

    Returns:
        A FakeLLMClient instance.
    """
    return FakeLLMClient(responses=responses)


def wire_response_generator(
    client: LLMClient | None = None,
    *,
    model: str = "fake-llm",
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> LLMResponseGenerator:
    """Wire a response generator.

    Args:
        client: Optional LLM client. When omitted, a fake client is used.
        model: Model name passed to the LLM provider.
        temperature: Sampling temperature passed to the LLM provider.
        max_tokens: Optional output token limit passed to the LLM provider.

    Returns:
        LLMResponseGenerator instance.
    """
    if client is None:
        client = wire_fake_llm_client()
    return LLMResponseGenerator(
        client,
        model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def wire_openai_llm_client(config: OpenAIConfig) -> LLMClient:
    """Wire an OpenAI LLM client.

    Args:
        config: OpenAI configuration.

    Returns:
        An OpenAILLMClient instance.
    """
    return OpenAILLMClient(config)


def wire_ollama_llm_client(config: OllamaConfig) -> LLMClient:
    """Wire an Ollama LLM client.

    Args:
        config: Ollama adapter configuration.

    Returns:
        An OllamaLLMClient instance.
    """
    return OllamaLLMClient(config)


class LLMClientFactory:
    """Explicit runtime factory for provider-specific LLM clients."""

    def __init__(self) -> None:
        """Create an explicit LLM client factory."""
        self._known_providers = ("fake", "ollama", "openai")

    def create_client(
        self,
        model_config: RuntimeModelConfig,
        runtime_config: IrisRuntimeConfig,
    ) -> LLMClient:
        """Create an LLM client for a runtime model slot.

        Args:
            model_config: Model slot configuration.
            runtime_config: Full runtime configuration.

        Returns:
            Provider-neutral LLM client.

        Raises:
            ConfigError: If the configured provider is unknown.
        """
        if model_config.provider not in self._known_providers:
            message = f"Unknown LLM provider: {model_config.provider}"
            raise ConfigError(message)
        if model_config.provider == "fake":
            return FakeLLMClient(model=model_config.model)
        if model_config.provider == "ollama":
            return OllamaLLMClient(_ollama_adapter_config(model_config, runtime_config))
        return OpenAILLMClient(_openai_adapter_config(model_config, runtime_config))

    def resolve_model(
        self,
        model_config: RuntimeModelConfig,
        runtime_config: IrisRuntimeConfig,
    ) -> str:
        """Resolve the model name sent in provider-neutral LLMRequest.

        Args:
            model_config: Model slot configuration.
            runtime_config: Full runtime configuration.

        Returns:
            Model name to pass into response generation.

        Raises:
            ConfigError: If the configured provider is unknown.
        """
        if model_config.provider not in self._known_providers:
            message = f"Unknown LLM provider: {model_config.provider}"
            raise ConfigError(message)
        if model_config.provider == "ollama":
            return _ollama_adapter_config(model_config, runtime_config).model
        if model_config.provider == "openai":
            return _openai_adapter_config(model_config, runtime_config).model
        return model_config.model


def _ollama_adapter_config(
    model_config: RuntimeModelConfig,
    runtime_config: IrisRuntimeConfig,
) -> OllamaConfig:
    model = model_config.model
    if model == "fake-llm":
        model = OllamaConfig().model
    return OllamaConfig(
        model=model,
        base_url=runtime_config.ollama.base_url,
        timeout_seconds=runtime_config.ollama.timeout_seconds,
        temperature=model_config.temperature,
        max_output_tokens=model_config.max_output_tokens,
        keep_alive=runtime_config.ollama.keep_alive,
    )


def _openai_adapter_config(
    model_config: RuntimeModelConfig,
    runtime_config: IrisRuntimeConfig,
) -> OpenAIConfig:
    model = model_config.model
    if model == "fake-llm":
        model = runtime_config.openai.model
    max_output_tokens = model_config.max_output_tokens
    if max_output_tokens is None:
        max_output_tokens = runtime_config.openai.max_output_tokens
    return OpenAIConfig.from_env(
        model=model,
        timeout_seconds=runtime_config.openai.timeout_seconds,
        max_output_tokens=max_output_tokens,
    )


def _build_user_content(prompt: ResponsePrompt) -> str:
    sections: list[str] = []
    if prompt.memory_snippets:
        snippets = "\n".join(f"- {snippet}" for snippet in prompt.memory_snippets)
        sections.append(f"Relevant memories:\n{snippets}")
    if prompt.affect_context is not None:
        sections.append(f"Affect context:\n{prompt.affect_context}")
    if prompt.relationship_context is not None:
        sections.append(f"Relationship context:\n{prompt.relationship_context}")
    if prompt.constraints:
        sections.append(f"Policy constraints: {'; '.join(prompt.constraints)}")
    if prompt.goals:
        sections.append(f"Goals: {'; '.join(prompt.goals)}")
    if not sections:
        return prompt.actor_text
    sections.append(f"Actor message:\n{prompt.actor_text}")
    return "\n\n".join(sections)
