"""Feature definition for event reaction."""

from __future__ import annotations

from iris.features.definition import FeatureDefinition
from iris.features.event_reaction.planner import EventReactionPlanner
from iris.features.event_reaction.policy import default_event_reaction_policy
from iris.features.event_reaction.presenter import EventReactionPresenter
from iris.features.event_reaction.templates import EventReactionTemplateProvider


def define_event_reaction_feature() -> FeatureDefinition:
    """イベントに対するリアクション機能の定義を返す。

    Returns:
        Event reaction vertical sliceの定義。
    """
    return FeatureDefinition(
        name="event_reaction",
        activity_reaction_planners=(
            EventReactionPlanner(
                policy=default_event_reaction_policy(),
                template_provider=EventReactionTemplateProvider(),
            ),
        ),
        action_plan_presenters=(EventReactionPresenter(),),
    )
