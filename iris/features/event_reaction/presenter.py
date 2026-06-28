"""イベント反応のアクションプランをPresentedOutputに変換するpresenter。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import override

from iris.contracts.actions import ActionPlan, PresentedOutput
from iris.contracts.presentation import ActionPlanPresenter


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
        return PresentedOutput(
            text=plan.candidate_text,
            priority=plan.priority,
            interruptible=plan.interruptible,
            style_hint="event_reaction",
        )
