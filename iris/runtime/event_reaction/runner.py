"""イベント反応を実行し、PresentedOutputに変換するrunner。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.actions import PresentedOutput
from iris.contracts.observations import ActivityEventObservation, Observation

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import SituationContextSnapshot
    from iris.runtime.event_reaction.planner import EventReactionPlanner


@dataclass(frozen=True)
class EventReactionRunner:
    """ActivityEventObservationに対して決定論的な反応を生成する。"""

    planner: EventReactionPlanner

    async def react(
        self,
        observation: Observation,
        *,
        situation_context: SituationContextSnapshot,
    ) -> PresentedOutput | None:
        """反応条件を満たせばPresentedOutputを返す。

        Args:
            observation: 処理対象の観測。
            situation_context: ランタイムから組み立てられた状況スナップショット。

        Returns:
            PresentedOutput | None: 反応があれば出力、なければNone。
        """
        if not isinstance(observation, ActivityEventObservation):
            return None

        decision = self.planner.plan(
            observation,
            situation_context=situation_context,
        )
        if not decision.should_react or decision.candidate is None:
            return None

        candidate = decision.candidate
        return PresentedOutput(
            text=candidate.text,
            priority=candidate.priority,
            interruptible=candidate.interruptible,
            style_hint="event_reaction",
        )
