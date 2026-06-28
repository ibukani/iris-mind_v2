"""Presentation suite."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.actions import PresentedOutput

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.contracts.actions import ActionPlan
    from iris.presentation.ports import ActionPlanPresenter


@dataclass(frozen=True)
class PresentationSuite:
    """Centralized presentation boundary."""

    presenters: Sequence[ActionPlanPresenter]

    async def present_action_plan(self, plan: ActionPlan) -> PresentedOutput:
        """アクションプランを処理可能なプレゼンターで提示する。

        Returns:
            PresentedOutput: 提示結果、処理可能なプレゼンターがない場合はno-send。
        """
        for presenter in self.presenters:
            if presenter.can_present(plan):
                return await presenter.present(plan)
        return PresentedOutput(text=None)
