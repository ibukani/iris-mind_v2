"""プロアクティブ発話のゴール提案ロジック。"""

from __future__ import annotations

from iris.contracts.actions import ActionPlan
from iris.features.proactive_talk.models import ProactiveGoal, ProactiveSalience


class GoalProposer:
    """顕著性スコアをプロアクティブゴールに変換する。"""

    @staticmethod
    def propose(salience: ProactiveSalience) -> ProactiveGoal:
        """与えられた顕著性スコアに基づいてゴールを提案する。

        Returns:
            ProactiveGoal: 顕著性スコアに基づく提案された目標。
        """
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
    """プロアクティブゴールをActionPlanに変換する。

    Returns:
        ActionPlan: 目標から変換されたアクションプラン。
    """
    return ActionPlan(
        turn_intent=goal.name,
        candidate_text=None,
        should_respond=goal.should_speak,
        priority=goal.priority,
    )
