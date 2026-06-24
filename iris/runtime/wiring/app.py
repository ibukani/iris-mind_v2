"""IrisApp のワイヤリング。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.ollama import OllamaConfig, OllamaLLMClient
from iris.adapters.llm.openai import OpenAIConfig, OpenAILLMClient
from iris.adapters.memory.sqlite import SQLiteMemoryStore
from iris.runtime.app import IrisApp
from iris.runtime.wiring.cognitive import (
    CognitiveCycleStores,
    CognitiveResponseOptions,
    wire_policy_affect_memory_aware_text_response_cognitive_cycle,
    wire_text_response_cognitive_cycle,
)
from iris.runtime.wiring.llm import LLMClientFactory
from iris.runtime.wiring.memory import (
    SQLiteFTS5MemoryRetriever,
    wire_sqlite_hybrid_memory_retriever,
)
from iris.runtime.wiring.presentation import wire_action_safety_gate, wire_output_safety_gate

if TYPE_CHECKING:
    from iris.adapters.llm.ports import LLMClient
    from iris.adapters.memory.vector_index import EmbeddingFunction
    from iris.cognitive.memory.retrieval import MemoryRetriever
    from iris.contracts.affect import AffectStore
    from iris.contracts.memory import MemoryStore, VectorMemoryIndex
    from iris.contracts.relationship import RelationshipStore
    from iris.runtime.config import IrisRuntimeConfig


def wire_default_app(
    llm_client: LLMClient,
    *,
    model: str = "fake-llm",
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> IrisApp:
    """標準的なテキスト応答向け認知サイクルを用いて IrisApp を組み立てる。

    Returns:
        完全に組み立てられた IrisApp。
    """
    cycle = wire_text_response_cognitive_cycle(
        llm_client,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return IrisApp(cycle=cycle)


def wire_fake_app(responses: tuple[str, ...] | None = None) -> IrisApp:
    """決定論的なフェイク LLM をバックエンドとする IrisApp を組み立てる。

    Returns:
        FakeLLMClient を使う IrisApp。
    """
    llm = FakeLLMClient(responses=responses)
    return wire_default_app(llm)


def wire_openai_app(
    config: OpenAIConfig | None = None,
    *,
    model: str = "gpt-5-mini",
) -> IrisApp:
    """OpenAI LLM クライアントをバックエンドとする IrisApp を組み立てる。

    Returns:
        OpenAI LLM client を使う IrisApp。
    """
    llm = OpenAILLMClient(config=config or OpenAIConfig.from_env(model=model))
    return wire_default_app(llm, model=model)


def wire_ollama_app(
    config: OllamaConfig | None = None,
    *,
    model: str = "llama3.2",
) -> IrisApp:
    """Ollama LLM クライアントをバックエンドとする IrisApp を組み立てる。

    Returns:
        Ollama LLM client を使う IrisApp。
    """
    llm = OllamaLLMClient(config=config)
    return wire_default_app(llm, model=model)


def build_app_from_config(
    config: IrisRuntimeConfig,
    *,
    client_factory: LLMClientFactory | None = None,
    memory_store: MemoryStore,
    relationship_store: RelationshipStore,
    affect_store: AffectStore,
    embed_text: EmbeddingFunction | None = None,
) -> IrisApp:
    """ランタイム設定から IrisApp を構築する。

    ``wire_runtime_state`` で組み立てた durable/ephemeral store を明示的に受け取り、
    cognitive pipeline へ constructor injection する。

    Returns:
        設定と runtime state store を注入済みの IrisApp。
    """
    model_config = config.models.default_chat
    factory = client_factory or LLMClientFactory()
    client = factory.create_client(model_config, config)
    model = factory.resolve_model(model_config, config)

    memory_retriever: MemoryRetriever | None = None
    vector_index: VectorMemoryIndex | None = None
    if isinstance(memory_store, SQLiteMemoryStore):
        if embed_text is not None:
            memory_retriever, vector_index = wire_sqlite_hybrid_memory_retriever(
                store=memory_store,
                embed_text=embed_text,
            )
        else:
            memory_retriever = SQLiteFTS5MemoryRetriever(memory_store)

    cycle = wire_policy_affect_memory_aware_text_response_cognitive_cycle(
        stores=CognitiveCycleStores(
            memory_store=memory_store,
            relationship_store=relationship_store,
            affect_store=affect_store,
            memory_retriever=memory_retriever,
            vector_index=vector_index,
        ),
        llm_client=client,
        response_options=CognitiveResponseOptions(
            model=model,
            temperature=model_config.temperature,
            max_tokens=model_config.max_output_tokens,
        ),
    )
    return IrisApp(
        cycle=cycle,
        action_safety_gate=wire_action_safety_gate(),
        output_safety_gate=wire_output_safety_gate(safety_config=config.safety),
    )
