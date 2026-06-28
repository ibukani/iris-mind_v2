"""アクションプランを出力として提示するためのプロトコルとデフォルト実装."""

from __future__ import annotations

from iris.contracts.actions import ActionPlan, PresentedOutput


class SimplePresenter:
    """アクションプランのフィールドをそのまま出力に委譲するデフォルトプレゼンター."""

    async def present(self, plan: ActionPlan) -> PresentedOutput:
        """アクションプランを提示用出力に変換する.

        Args:
            plan: The action plan to present.

        Returns:
            Presented output with text and metadata from the plan.
        """
        _ = self
        if plan.is_no_action:
            return PresentedOutput(text=None)
        return PresentedOutput(
            text=plan.candidate_text,
            priority=plan.priority,
            interruptible=plan.interruptible,
        )
