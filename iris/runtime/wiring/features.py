"""機能拡張された認知サイクル向けのワイヤリング関数。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.features.event_reaction import define_event_reaction_feature
from iris.features.proactive_talk import define_proactive_talk_feature
from iris.runtime.wiring.cognitive import (
    CognitiveCycleStores,
    wire_policy_affect_memory_aware_text_response_cognitive_cycle,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.cognitive.cycle.models import PipelineStepResult
    from iris.cognitive.cycle.pipeline import PipelineStep
    from iris.cognitive.cycle.service import CognitiveCycle
    from iris.contracts.memory import MemoryStore
    from iris.contracts.relationship import RelationshipStore
    from iris.features.definition import FeatureDefinition


@dataclass(frozen=True)
class RuntimeFeatureCatalog:
    """標準ランタイムで有効なフィーチャー定義の集合。"""

    features: tuple[FeatureDefinition, ...]


def wire_runtime_features() -> RuntimeFeatureCatalog:
    """標準ランタイムのフィーチャー集合を組み立てる。

    Returns:
        明示注入するフィーチャー定義の集合。
    """
    return RuntimeFeatureCatalog(
        features=(define_event_reaction_feature(),),
    )


def collect_cognitive_steps(
    features: Sequence[FeatureDefinition],
) -> tuple[PipelineStep[PipelineStepResult], ...]:
    """有効なフィーチャーの認知ステップを登録順に収集する。

    Args:
        features: composition root で有効化されたフィーチャー定義。

    Returns:
        CognitiveCycle の拡張位置へ注入する認知ステップ。
    """
    return tuple(step for feature in features for step in feature.cognitive_steps)


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
    return wire_policy_affect_memory_aware_text_response_cognitive_cycle(
        stores=CognitiveCycleStores(
            memory_store=memory_store,
            relationship_store=relationship_store,
        ),
        extension_steps=collect_cognitive_steps((feature,)),
    )
