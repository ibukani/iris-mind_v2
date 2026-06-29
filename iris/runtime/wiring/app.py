"""IrisApp のワイヤリング。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.adapters.persistence.sqlite.stores.memory import SQLiteMemoryStore
from iris.contracts.llm import DEFAULT_FAKE_LLM_MODEL
from iris.features.basic_action.definition import define_basic_action_feature
from iris.features.chat.definition import define_chat_feature
from iris.runtime.app import IrisApp
from iris.runtime.wiring.cognitive import (
    CognitiveCycleStores,
    wire_basic_cognitive_cycle,
    wire_core_cognitive_cycle,
)
from iris.runtime.wiring.features import (
    collect_action_plan_presenters,
    collect_cognitive_steps,
)
from iris.runtime.wiring.llm import LLMClientFactory, wire_response_generator
from iris.runtime.wiring.memory import SQLiteFTS5MemoryRetriever
from iris.runtime.wiring.presentation import wire_output_pipeline

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.adapters.llm.ports import LLMClient
    from iris.cognitive.memory.retrieval import MemoryRetriever
    from iris.contracts.affect import AffectStore
    from iris.contracts.memory import MemoryStore
    from iris.contracts.relationship import RelationshipStore
    from iris.features.definition import FeatureDefinition
    from iris.runtime.config import IrisRuntimeConfig
    from iris.runtime.output_pipeline import RuntimeOutputPipeline


@dataclass(frozen=True)
class AppStateDependencies:
    """標準 IrisApp の認知サイクルへ注入する state 依存。"""

    memory_store: MemoryStore
    relationship_store: RelationshipStore
    affect_store: AffectStore


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
    chat_feature = define_chat_feature(
        wire_response_generator(
            llm_client,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    )
    basic_action_feature = define_basic_action_feature()
    features = [chat_feature, basic_action_feature]
    cycle = wire_basic_cognitive_cycle(extension_steps=collect_cognitive_steps(features))
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

    chat_feature = define_chat_feature(
        wire_response_generator(
            client,
            model=model,
            temperature=model_config.temperature,
            max_tokens=model_config.max_output_tokens,
        )
    )
    all_features = [*list(features), chat_feature]

    cycle = wire_core_cognitive_cycle(
        stores=CognitiveCycleStores(
            memory_store=state.memory_store,
            relationship_store=state.relationship_store,
            affect_store=state.affect_store,
            memory_retriever=memory_retriever,
            vector_index=None,
        ),
        extension_steps=collect_cognitive_steps(all_features),
    )
    return IrisApp(
        cycle=cycle,
        output_pipeline=output_pipeline,
    )
