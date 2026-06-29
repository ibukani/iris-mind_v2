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
from iris.contracts.llm import DEFAULT_FAKE_LLM_MODEL
from iris.contracts.memory import MemoryStore, MutableMemoryStore, VectorMemoryIndex
from iris.runtime.state.ephemeral.affect import InMemoryAffectStore
from iris.runtime.state.ephemeral.relationship import InMemoryRelationshipStore

if TYPE_CHECKING:
    from collections.abc import Sequence

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
    """応答生成ステップへ渡す LLM 設定。(Deprecated: use Chat Feature instead)"""

    model: str = DEFAULT_FAKE_LLM_MODEL
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


def wire_basic_cognitive_cycle(
    *, extension_steps: Sequence[PipelineStep[PipelineStepResult]] = ()
) -> CognitiveCycle:
    """デフォルトの最小構成の認知サイクルを組み立てる。

    Returns:
        知覚ステップと拡張ステップを持つ CognitiveCycle。
    """
    steps: list[PipelineStep[PipelineStepResult]] = [SimplePerceptionStep()]
    steps.extend(extension_steps)
    return wire_cognitive_cycle(steps=steps)


def wire_memory_aware_cognitive_cycle(
    memory_store: MemoryStore,
    *,
    extension_steps: Sequence[PipelineStep[PipelineStepResult]] = (),
) -> CognitiveCycle:
    """メモリ検索付き認知サイクルを組み立てる。

    Returns:
        メモリ検索ステップを持つ CognitiveCycle。
    """
    steps: list[PipelineStep[PipelineStepResult]] = [
        SimplePerceptionStep(),
        MemoryRetrievalStep(memory_store),
    ]
    steps.extend(extension_steps)
    return wire_cognitive_cycle(steps=steps)


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


def _build_affect_memory_steps(
    stores: CognitiveCycleStores,
) -> list[PipelineStep[PipelineStepResult]]:
    """Memory、affect、relationship の共通 step 群を組み立てる。

    Returns:
        perception から relationship 更新までの pipeline step。
    """
    affect_store = stores.affect_store or InMemoryAffectStore()
    steps: list[PipelineStep[PipelineStepResult]] = [SimplePerceptionStep()]
    steps.extend(_build_memory_steps(stores))
    steps.extend(
        (
            AffectBaselineLoadStep(affect_store),
            AppraisalStep(),
            AffectPersistenceStep(affect_store),
            RelationshipStep(stores.relationship_store or InMemoryRelationshipStore()),
        ),
    )
    return steps


def wire_affect_memory_aware_cognitive_cycle(
    stores: CognitiveCycleStores | None = None,
    *,
    extension_steps: Sequence[PipelineStep[PipelineStepResult]] = (),
) -> CognitiveCycle:
    """メモリ、感情、関係性を使う認知サイクルを組み立てる。

    Returns:
        affect/relationship persistence を持つ CognitiveCycle。
    """
    stores = stores or CognitiveCycleStores()
    steps = _build_affect_memory_steps(stores)
    steps.extend(extension_steps)
    return wire_cognitive_cycle(steps=steps)


def wire_core_cognitive_cycle(
    stores: CognitiveCycleStores | None = None,
    *,
    extension_steps: Sequence[PipelineStep[PipelineStepResult]] = (),
) -> CognitiveCycle:
    """Policy inhibition 付きの感情・メモリ対応認知サイクルを組み立てる。

    Returns:
        memory → appraisal → persistence → policy → feature extension の CognitiveCycle。
    """
    stores = stores or CognitiveCycleStores()
    steps = _build_affect_memory_steps(stores)
    steps.append(PolicyInhibitionStep())
    steps.extend(extension_steps)
    return wire_cognitive_cycle(steps=steps)
