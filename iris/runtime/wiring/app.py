"""Constructor-injection-only composition for the default IrisApp.

No service locator, no global registry, no cognitive policy logic.
"""

from __future__ import annotations

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.openai import OpenAIConfig, OpenAILLMClient
from iris.adapters.llm.ports import LLMClient
from iris.runtime.app import IrisApp
from iris.runtime.wiring.cognitive import wire_text_response_cognitive_cycle


def wire_default_app(llm_client: LLMClient | None = None) -> IrisApp:
    cycle = wire_text_response_cognitive_cycle(llm_client)
    return IrisApp(cycle=cycle)


def wire_fake_app(responses: tuple[str, ...] | None = None) -> IrisApp:
    llm = FakeLLMClient(responses=responses)
    return wire_default_app(llm)


def wire_openai_app(
    config: OpenAIConfig | None = None,
    *,
    model: str = "gpt-5-mini",
) -> IrisApp:
    if config is None:
        config = OpenAIConfig.from_env(model=model)
    return wire_default_app(OpenAILLMClient(config))
