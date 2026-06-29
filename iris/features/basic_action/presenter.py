"""アクションプランを出力として提示するためのプロトコルとデフォルト実装."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.contracts.actions import presented_output_from_plan
from iris.contracts.presentation import ActionPlanPresenter

if TYPE_CHECKING:
    from iris.contracts.actions import ActionPlan, PresentedOutput


class SimplePresenter(ActionPlanPresenter):
    """アクションプランのフィールドをそのまま出力に委譲するデフォルトプレゼンター."""

    @override
    def can_present(self, plan: ActionPlan) -> bool:
        """event_reactionなど専用Presenterがあるものを除きTrueを返す.

        Returns:
            bool: event_reaction以外であればTrue.
        """
        return plan.turn_intent != "event_reaction"

    @override
    async def present(self, plan: ActionPlan) -> PresentedOutput:
        """アクションプランを提示用出力に変換する.

        Args:
            plan: The action plan to present.

        Returns:
            Presented output with text and metadata from the plan.
        """
        _ = self
        return presented_output_from_plan(plan)
