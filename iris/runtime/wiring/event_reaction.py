"""EventReactionRunnerのwiring helper。"""

from __future__ import annotations

from iris.runtime.event_reaction.planner import EventReactionPlanner
from iris.runtime.event_reaction.policy import default_event_reaction_policy
from iris.runtime.event_reaction.runner import EventReactionRunner


def wire_event_reaction_runner() -> EventReactionRunner:
    """デフォルトポリシーでEventReactionRunnerを組み立てる。

    Returns:
        EventReactionRunner: 配線済みのrunner。
    """
    return EventReactionRunner(
        planner=EventReactionPlanner(policy=default_event_reaction_policy()),
    )
