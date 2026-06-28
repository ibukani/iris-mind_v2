"""イベント反応（event reaction）の決定パイプライン。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.contracts.actions import ActionPlan
    from iris.contracts.observations import ActivityEventObservation
    from iris.contracts.workspace_context import SituationContextSnapshot
    from iris.features.definition import ActivityReactionPlanner


@dataclass(frozen=True)
class EventReactionDecisionPipeline:
    """ActivityEventObservationに対して決定論的な反応を計画する。"""

    planners: Sequence[ActivityReactionPlanner]

    async def decide(
        self,
        observation: ActivityEventObservation,
        *,
        situation_context: SituationContextSnapshot,
    ) -> ActionPlan | None:
        """プランナーを順に実行し、ActionPlanを返す。

        Args:
            observation: 処理対象の観測。
            situation_context: ランタイムから組み立てられた状況スナップショット。

        Returns:
            ActionPlan | None: 反応候補があればそれ、なければNone。
        """
        for planner in self.planners:
            decision = planner.plan(
                observation,
                availability=situation_context.availability,
            )
            if decision.should_react and decision.candidate is not None:
                return decision.candidate

        return None
