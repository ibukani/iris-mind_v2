"""IrisApp のワイヤリング。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.adapters.persistence.sqlite.stores.memory import SQLiteMemoryStore
from iris.adapters.rerankers.rule import RuleBasedReranker
from iris.contracts.llm import DEFAULT_FAKE_LLM_MODEL
from iris.features.chat.definition import define_chat_feature
from iris.runtime.app import IrisApp
from iris.runtime.wiring.cognitive import (
    CognitiveCycleStores,
    CognitiveSemanticsOptions,
    wire_basic_cognitive_cycle,
    wire_core_cognitive_cycle,
)
from iris.runtime.wiring.features import (
    collect_action_plan_presenters,
    collect_cognitive_steps,
    collect_feature_items,
)
from iris.runtime.wiring.llm import (
    LLMClientFactory,
    ResponseGeneratorWiringOptions,
    wire_budgeted_response_generator,
    wire_response_generator,
)
from iris.runtime.wiring.memory import (
    SemanticMemoryRetrieverWiringDependencies,
    SemanticMemoryRetrieverWiringOptions,
    SQLiteFTS5MemoryRetriever,
    wire_hybrid_memory_retriever,
    wire_semantic_memory_retriever,
)
from iris.runtime.wiring.presentation import wire_output_pipeline

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.adapters.llm.ports import LLMClient
    from iris.cognitive.memory.retrieval import MemoryRetriever
    from iris.contracts.affect import AffectStore
    from iris.contracts.embeddings import EmbeddingClient
    from iris.contracts.memory import MemoryStore, VectorMemoryIndex
    from iris.contracts.relationship import RelationshipStore
    from iris.features.definition import FeatureDefinition
    from iris.runtime.config import IrisRuntimeConfig
    from iris.runtime.config.model_call_budget import RuntimeModelCallBudgetConfig
    from iris.runtime.config.prompt_budget import RuntimePromptBudgetConfig
    from iris.runtime.inference.scheduler import LocalInferenceResourceScheduler
    from iris.runtime.output_pipeline import RuntimeOutputPipeline


@dataclass(frozen=True)
class ChatFeatureWiringOptions:
    """Chat feature wiring に必要な LLM 周辺設定。"""

    model: str
    temperature: float
    max_tokens: int | None
    model_call_budget: RuntimeModelCallBudgetConfig | None = None
    prompt_budget: RuntimePromptBudgetConfig | None = None
    inference_scheduler: LocalInferenceResourceScheduler | None = None


@dataclass(frozen=True)
class AppStateDependencies:
    """標準 IrisApp の認知サイクルへ注入する state 依存。"""

    memory_store: MemoryStore
    relationship_store: RelationshipStore
    affect_store: AffectStore
    vector_index: VectorMemoryIndex | None = None
    embedding: EmbeddingClient | None = None


def wire_default_app(
    llm_client: LLMClient,
    *,
    model: str = DEFAULT_FAKE_LLM_MODEL,
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> IrisApp:
    """標準的なテキスト応答向け認知サイクルを用いて IrisApp を組み立てる。

    Returns:
        完全に組み立てられた IrisApp。
    """
    chat_feature = _wire_chat_feature(
        llm_client,
        ChatFeatureWiringOptions(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        ),
    )
    features = (chat_feature,)
    cycle = wire_basic_cognitive_cycle(
        extension_steps=collect_cognitive_steps(features),
    )
    output_pipeline = wire_output_pipeline(
        extension_presenters=collect_action_plan_presenters(features),
    )
    return IrisApp(cycle=cycle, output_pipeline=output_pipeline)


def build_app_from_config(
    config: IrisRuntimeConfig,
    *,
    client_factory: LLMClientFactory | None = None,
    state: AppStateDependencies,
    output_pipeline: RuntimeOutputPipeline,
    features: Sequence[FeatureDefinition] = (),
    inference_scheduler: LocalInferenceResourceScheduler | None = None,
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
    if isinstance(state.memory_store, SQLiteMemoryStore):
        memory_retriever = SQLiteFTS5MemoryRetriever(state.memory_store)
        if state.vector_index is not None and state.embedding is not None:
            if config.memory.retrieval.semantic_enabled:
                memory_retriever = wire_semantic_memory_retriever(
                    SemanticMemoryRetrieverWiringDependencies(
                        fts_retriever=memory_retriever,
                        vector_index=state.vector_index,
                        embedding=state.embedding,
                        reranker=RuleBasedReranker(),
                        store=state.memory_store,
                    ),
                    SemanticMemoryRetrieverWiringOptions(
                        retrieval_config=config.memory.retrieval,
                        prompt_budget_config=config.prompt_budget,
                        prompt_profile=config.prompt_budget.chat_profile,
                    ),
                )
            else:
                memory_retriever = wire_hybrid_memory_retriever(
                    fts_retriever=memory_retriever,
                    vector_index=state.vector_index,
                    embedding=state.embedding,
                    store=state.memory_store,
                )

    chat_feature = _wire_chat_feature(
        client,
        ChatFeatureWiringOptions(
            model=model,
            temperature=model_config.temperature,
            max_tokens=model_config.max_output_tokens,
            model_call_budget=config.model_call_budget,
            prompt_budget=config.prompt_budget,
            inference_scheduler=inference_scheduler,
        ),
    )
    all_features = collect_feature_items((features, (chat_feature,)))
    cycle = wire_core_cognitive_cycle(
        stores=CognitiveCycleStores(
            memory_store=state.memory_store,
            relationship_store=state.relationship_store,
            affect_store=state.affect_store,
            memory_retriever=memory_retriever,
            vector_index=state.vector_index,
            embedding=state.embedding,
            fail_open_on_index_error=config.memory.vector.fail_open_on_index_error,
        ),
        extension_steps=collect_cognitive_steps(all_features),
        semantics=CognitiveSemanticsOptions(config=config.companion_semantics),
    )
    return IrisApp(cycle=cycle, output_pipeline=output_pipeline)


def _wire_chat_feature(
    llm_client: LLMClient,
    options: ChatFeatureWiringOptions,
) -> FeatureDefinition:
    """Chat feature を再利用可能な形で組み立てる。

    Returns:
        構成済みの chat feature。
    """
    generator = wire_response_generator(
        llm_client,
        options=ResponseGeneratorWiringOptions(
            model=options.model,
            temperature=options.temperature,
            max_tokens=options.max_tokens,
            prompt_budget_config=options.prompt_budget,
            inference_scheduler=options.inference_scheduler,
        ),
    )
    if options.model_call_budget is not None:
        return define_chat_feature(
            wire_budgeted_response_generator(
                generator,
                options.model_call_budget,
                model=options.model,
                model_slot="default_chat",
            )
        )
    return define_chat_feature(generator)
