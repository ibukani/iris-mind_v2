from __future__ import annotations

from iris.contracts.actions import ActionPlan
from iris.features.proactive_talk.models import ProactiveGoal, ProactiveSalience


class GoalProposer:
    def propose(self, salience: ProactiveSalience) -> ProactiveGoal:
        if not salience.should_speak:
            reason = "blocked" if salience.blocked else "below_threshold"
            return ProactiveGoal(name="no_action", reason=reason, should_speak=False)

        return ProactiveGoal(
            name="proactive_talk",
            reason="salience_above_threshold",
            should_speak=True,
            priority=int(salience.score * 100),
        )


def action_plan_from_goal(goal: ProactiveGoal) -> ActionPlan:
    return ActionPlan(
        turn_intent=goal.name,
        candidate_text=None,
        should_respond=goal.should_speak,
        priority=goal.priority,
    )
