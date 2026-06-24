"""EventReactionRunnerのwiring helper。"""

from __future__ import annotations

from iris.features.event_reaction.planner import EventReactionPlanner
from iris.features.event_reaction.policy import default_event_reaction_policy
from iris.features.event_reaction.templates import EventReactionTemplateProvider
from iris.presentation.event_reaction import EventReactionPresenter
from iris.runtime.ingress.activity_event_reaction_runner import EventReactionRunner


def wire_event_reaction_runner() -> EventReactionRunner:
    """デフォルトポリシーでEventReactionRunnerを組み立てる。

    Returns:
        EventReactionRunner: 配線済みのrunner。
    """
    template_provider = EventReactionTemplateProvider()
    return EventReactionRunner(
        planner=EventReactionPlanner(
            policy=default_event_reaction_policy(),
            template_provider=template_provider,
        ),
        presenter=EventReactionPresenter(),
    )
