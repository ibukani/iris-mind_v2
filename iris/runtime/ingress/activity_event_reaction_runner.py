"""イベント反応を実行し、PresentedOutputに変換するrunner。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import SituationContextSnapshot
    from iris.contracts.actions import PresentedOutput
    from iris.contracts.observations import ActivityEventObservation
    from iris.features.event_reaction.planner import EventReactionPlanner
    from iris.presentation.event_reaction import EventReactionPresenter


@dataclass(frozen=True)
class EventReactionRunner:
    """ActivityEventObservationに対して決定論的な反応を生成する。"""

    planner: EventReactionPlanner
    presenter: EventReactionPresenter

    async def react(
        self,
        observation: ActivityEventObservation,
        *,
        situation_context: SituationContextSnapshot,
    ) -> PresentedOutput | None:
        """反応条件を満たせばPresentedOutputを返す。

        Args:
            observation: 処理処理対象の観測。
            situation_context: ランタイムから組み立てられた状況スナップショット。

        Returns:
            PresentedOutput | None: 反応があれば出力、なければNone。
        """
        decision = self.planner.plan(
            observation,
            availability=situation_context.availability,
        )
        if not decision.should_react or decision.candidate is None:
            return None

        return self.presenter.present(decision.candidate)
