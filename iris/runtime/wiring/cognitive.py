"""認知サイクルのワイヤリング。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.cognitive.affect.appraisal import AppraisalStep
from iris.cognitive.affect.persistence import AffectBaselineLoadStep, AffectPersistenceStep
from iris.cognitive.affect.relationship import RelationshipStep
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.service import CognitiveCycle
from iris.cognitive.memory.retrieval import MemoryRetrievalStep, MemoryRetriever
from iris.cognitive.memory.write import MemoryWriteStep
from iris.cognitive.perception.basic import SimplePerceptionStep
from iris.cognitive.policy.inhibition import PolicyInhibitionStep
from iris.contracts.actions import ActionPlan
from iris.contracts.memory import MemoryStore, MutableMemoryStore, VectorMemoryIndex
from iris.features.chat.definition import ResponseGenerationStep
from iris.runtime.state.ephemeral.affect import InMemoryAffectStore
from iris.runtime.state.ephemeral.relationship import InMemoryRelationshipStore
from iris.runtime.wiring.llm import wire_response_generator

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.adapters.llm.ports import LLMClient
    from iris.cognitive.cycle.models import PipelineStepResult
    from iris.cognitive.cycle.pipeline import PipelineStep
    from iris.contracts.affect import AffectStore
    from iris.contracts.relationship import RelationshipStore


@dataclass(frozen=True)
class CognitiveCycleStores:
    """認知サイクルに注入する state store 群。"""

    memory_store: MemoryStore | None = None
    relationship_store: RelationshipStore | None = None
    affect_store: AffectStore | None = None
    memory_retriever: MemoryRetriever | None = None
    vector_index: VectorMemoryIndex | None = None


@dataclass(frozen=True)
class CognitiveResponseOptions:
    """応答生成ステップへ渡す LLM 設定。"""

    model: str = "fake-llm"
    temperature: float = 0.0
    max_tokens: int | None = None


def wire_cognitive_cycle(
    steps: Sequence[PipelineStep[PipelineStepResult]],
    fallback_plan: ActionPlan | None = None,
) -> CognitiveCycle:
    """明示的なパイプラインステップから CognitiveCycle を組み立てる。

    Returns:
        構成済みの CognitiveCycle。
    """
    if fallback_plan is None:
        fallback_plan = ActionPlan.no_action()
    return CognitiveCycle(
        steps=steps,
        frame_builder=FrameBuilder(),
        fallback_plan=fallback_plan,
    )


def wire_text_response_cognitive_cycle(
    llm_client: LLMClient | None = None,
    *,
    model: str = "fake-llm",
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> CognitiveCycle:
    """デフォルトの 1 ターンテキスト応答向け認知サイクルを組み立てる。

    Returns:
        知覚と応答生成ステップを持つ CognitiveCycle。
    """
    return wire_cognitive_cycle(
        steps=(
            SimplePerceptionStep(),
            ResponseGenerationStep(
                wire_response_generator(
                    llm_client,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
            ),
        ),
    )


def wire_memory_aware_text_response_cognitive_cycle(
    memory_store: MemoryStore,
    llm_client: LLMClient | None = None,
    *,
    model: str = "fake-llm",
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> CognitiveCycle:
    """メモリ検索付きテキスト応答向け認知サイクルを組み立てる。

    Returns:
        メモリ検索と応答生成ステップを持つ CognitiveCycle。
    """
    steps = [
        SimplePerceptionStep(),
        MemoryRetrievalStep(memory_store),
        ResponseGenerationStep(
            wire_response_generator(
                llm_client,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            ),
        ),
    ]
    return wire_cognitive_cycle(steps=tuple(steps))


def _build_memory_steps(
    stores: CognitiveCycleStores,
) -> list[PipelineStep[PipelineStepResult]]:
    """設定に応じて retrieval/write の memory step を組み立てる。

    Returns:
        実行順に並んだ memory pipeline step。
    """
    steps: list[PipelineStep[PipelineStepResult]] = []
    if stores.memory_retriever is not None:
        steps.append(MemoryRetrievalStep(stores.memory_retriever))
    elif stores.memory_store is not None:
        steps.append(MemoryRetrievalStep(stores.memory_store))

    if isinstance(stores.memory_store, MutableMemoryStore):
        steps.append(
            MemoryWriteStep(
                stores.memory_store,
                vector_index=stores.vector_index,
            ),
        )
    return steps


def wire_affect_memory_aware_text_response_cognitive_cycle(
    stores: CognitiveCycleStores | None = None,
    llm_client: LLMClient | None = None,
    *,
    response_options: CognitiveResponseOptions | None = None,
) -> CognitiveCycle:
    """メモリ、感情、関係性を使うテキスト応答向け認知サイクルを組み立てる。

    Returns:
        affect/relationship persistence と応答生成を持つ CognitiveCycle。
    """
    stores = stores or CognitiveCycleStores()
    options = response_options or CognitiveResponseOptions()
    affect_store = stores.affect_store or InMemoryAffectStore()
    response_generator = ResponseGenerationStep(
        wire_response_generator(
            llm_client,
            model=options.model,
            temperature=options.temperature,
            max_tokens=options.max_tokens,
        ),
    )
    steps: list[PipelineStep[PipelineStepResult]] = [SimplePerceptionStep()]
    steps.extend(_build_memory_steps(stores))
    steps.extend(
        (
            AffectBaselineLoadStep(affect_store),
            AppraisalStep(),
            AffectPersistenceStep(affect_store),
            RelationshipStep(stores.relationship_store or InMemoryRelationshipStore()),
            response_generator,
        ),
    )
    return wire_cognitive_cycle(steps=tuple(steps))


def wire_policy_affect_memory_aware_text_response_cognitive_cycle(
    stores: CognitiveCycleStores | None = None,
    llm_client: LLMClient | None = None,
    *,
    response_options: CognitiveResponseOptions | None = None,
    extension_steps: Sequence[PipelineStep[PipelineStepResult]] = (),
) -> CognitiveCycle:
    """Policy inhibition 付きの感情・メモリ対応テキスト応答サイクルを組み立てる。

    Returns:
        memory → appraisal → persistence → policy → feature extension → response の CognitiveCycle。
    """
    stores = stores or CognitiveCycleStores()
    options = response_options or CognitiveResponseOptions()
    affect_store = stores.affect_store or InMemoryAffectStore()
    response_generator = ResponseGenerationStep(
        wire_response_generator(
            llm_client,
            model=options.model,
            temperature=options.temperature,
            max_tokens=options.max_tokens,
        ),
    )
    steps: list[PipelineStep[PipelineStepResult]] = [SimplePerceptionStep()]
    steps.extend(_build_memory_steps(stores))
    steps.extend(
        (
            AffectBaselineLoadStep(affect_store),
            AppraisalStep(),
            AffectPersistenceStep(affect_store),
            RelationshipStep(stores.relationship_store or InMemoryRelationshipStore()),
            PolicyInhibitionStep(),
        ),
    )
    steps.extend(extension_steps)
    steps.append(response_generator)
    return wire_cognitive_cycle(steps=tuple(steps))
