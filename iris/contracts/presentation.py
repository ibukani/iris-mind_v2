"""Presentation ports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from iris.contracts.actions import ActionPlan, PresentedOutput


class ActionPlanPresenter(Protocol):
    """ActionPlanをPresentedOutputに変換するプロトコル。"""

    def can_present(self, plan: ActionPlan) -> bool:
        """このプレゼンターが与えられたActionPlanを処理できるか判定する。"""
        ...

    async def present(self, plan: ActionPlan) -> PresentedOutput:
        """ActionPlanを提示可能な出力へ変換する。"""
        ...
