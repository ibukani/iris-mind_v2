"""汎用 ActionPlan presenter。"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.contracts.actions import presented_output_from_plan
from iris.contracts.presentation import ActionPlanPresenter

if TYPE_CHECKING:
    from iris.contracts.actions import ActionPlan, PresentedOutput


class DefaultActionPlanPresenter(ActionPlanPresenter):
    """専用 presenter が扱わない通常 ActionPlan を PresentedOutput に変換する。"""

    @override
    def can_present(self, plan: ActionPlan) -> bool:
        """event_reaction など専用 presenter がある intent は扱わない。

        Returns:
            専用 presenter に委譲すべき intent でなければ True。
        """
        return plan.turn_intent != "event_reaction"

    @override
    async def present(self, plan: ActionPlan) -> PresentedOutput:
        """ActionPlan を提示用出力へ変換する。

        Returns:
            plan の text / metadata を引き継ぐ提示用出力。
        """
        _ = self
        return presented_output_from_plan(plan)
