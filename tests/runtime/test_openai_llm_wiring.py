from __future__ import annotations

from iris.adapters.llm.openai import OpenAIConfig, OpenAILLMClient
from iris.adapters.llm.ports import LLMClient
from iris.runtime.wiring.llm import wire_openai_llm_client


def test_openai_wiring_returns_llm_client_compatible_instance() -> None:
    client = wire_openai_llm_client(OpenAIConfig(model="gpt-test", api_key="test-key"))

    assert isinstance(client, OpenAILLMClient)
    assert hasattr(client, "generate")


def test_openai_wiring_return_can_be_typed_as_llm_client() -> None:
    client: LLMClient = wire_openai_llm_client(OpenAIConfig(model="gpt-test", api_key="test-key"))

    assert client is not None
