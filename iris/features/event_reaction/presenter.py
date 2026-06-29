"""イベント反応のアクションプランをPresentedOutputに変換するpresenter。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from iris.contracts.actions import presented_output_from_plan
from iris.contracts.presentation import ActionPlanPresenter

if TYPE_CHECKING:
    from iris.contracts.actions import ActionPlan, PresentedOutput


@dataclass(frozen=True)
class EventReactionPresenter(ActionPlanPresenter):
    """イベント反応用のアクションプランをPresentedOutputに変換する。"""

    @override
    def can_present(self, plan: ActionPlan) -> bool:
        """turn_intentがevent_reactionであるか判定する。

        Returns:
            bool: event_reactionである場合はTrue。
        """
        return plan.turn_intent == "event_reaction"

    @override
    async def present(self, plan: ActionPlan) -> PresentedOutput:
        """候補からPresentedOutputを生成する。

        Returns:
            PresentedOutput: 変換された出力。
        """
        return presented_output_from_plan(plan, style_hint="event_reaction")
