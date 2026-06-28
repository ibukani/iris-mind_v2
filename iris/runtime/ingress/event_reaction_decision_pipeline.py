"""イベント反応（event reaction）の決定パイプライン。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import SituationContextSnapshot
    from iris.contracts.event_reaction import ReactionCandidate
    from iris.contracts.observations import ActivityEventObservation
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
    ) -> ReactionCandidate | None:
        """プランナーを順に実行し、ReactionCandidateを返す。

        Args:
            observation: 処理対象の観測。
            situation_context: ランタイムから組み立てられた状況スナップショット。

        Returns:
            ReactionCandidate | None: 反応候補があればそれ、なければNone。
        """
        for planner in self.planners:
            decision = planner.plan(
                observation,
                availability=situation_context.availability,
            )
            if decision.should_react and decision.candidate is not None:
                return decision.candidate

        return None
