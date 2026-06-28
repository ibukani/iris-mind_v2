"""Event reaction wiring helper."""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.runtime.ingress.event_reaction_decision_pipeline import EventReactionDecisionPipeline

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.features.definition import FeatureDefinition


def wire_event_reaction_decision_pipeline(
    features: Sequence[FeatureDefinition],
) -> EventReactionDecisionPipeline:
    """FeatureDefinitions から EventReactionDecisionPipeline を組み立てる。

    Args:
        features: 登録されたフィーチャーのリスト。

    Returns:
        EventReactionDecisionPipeline: 配線済みの decision pipeline。
    """
    planners = []
    for feature in features:
        planners.extend(feature.activity_reaction_planners)
    
    return EventReactionDecisionPipeline(planners=tuple(planners))
