"""機能拡張された認知サイクル向けのワイヤリング関数。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.relationship.memory import InMemoryRelationshipStore
from iris.cognitive.affect.appraisal import AppraisalStep
from iris.cognitive.affect.relationship import RelationshipStep
from iris.cognitive.memory.retrieval import MemoryRetrievalStep
from iris.cognitive.perception.basic import SimplePerceptionStep
from iris.cognitive.policy.inhibition import PolicyInhibitionStep
from iris.features.proactive_talk import define_proactive_talk_feature
from iris.runtime.wiring.cognitive import wire_cognitive_cycle

if TYPE_CHECKING:
    from iris.adapters.memory.ports import MemoryStore
    from iris.cognitive.cycle.models import PipelineStepResult
    from iris.cognitive.cycle.pipeline import PipelineStep
    from iris.cognitive.cycle.service import CognitiveCycle
    from iris.contracts.relationship import RelationshipStore
    from iris.features.definition import FeatureDefinition


def wire_proactive_talk_feature(salience_threshold: float = 0.5) -> FeatureDefinition:
    """Proactive talk 機能の定義を組み立てる。

    Args:
        salience_threshold: 能動的開始を行うためのサリエンス最小値。

    Returns:
        proactive talk 用の FeatureDefinition。
    """
    return define_proactive_talk_feature(salience_threshold=salience_threshold)


def wire_proactive_talk_cognitive_cycle(
    memory_store: MemoryStore | None = None,
    relationship_store: RelationshipStore | None = None,
    salience_threshold: float = 0.5,
) -> CognitiveCycle:
    """Proactive talk 機能で拡張された認知サイクルを組み立てる。

    Args:
        memory_store: 任意の取得用メモリストア。
        relationship_store: 任意の共有関係性 state store。
        salience_threshold: 能動的開始を行うためのサリエンス最小値。

    Returns:
        知覚・メモリ・感情・ポリシー・proactive talk パイプラインステップを含む CognitiveCycle。
    """
    feature = wire_proactive_talk_feature(salience_threshold=salience_threshold)
    steps: list[PipelineStep[PipelineStepResult]] = [SimplePerceptionStep()]
    if memory_store is not None:
        steps.append(MemoryRetrievalStep(memory_store))
    steps.extend(
        (
            AppraisalStep(),
            RelationshipStep(relationship_store or InMemoryRelationshipStore()),
            PolicyInhibitionStep(),
            *feature.pipeline_steps,
        )
    )
    return wire_cognitive_cycle(steps=tuple(steps))
