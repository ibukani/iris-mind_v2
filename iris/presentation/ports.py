"""Presentation ports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from iris.contracts.actions import ActionPlan, PresentedOutput
    from iris.contracts.event_reaction import ReactionCandidate


class ActionPlanPresenter(Protocol):
    """ActionPlanをPresentedOutputに変換するプロトコル。"""

    async def present(self, plan: ActionPlan) -> PresentedOutput:
        """ActionPlanを提示可能な出力へ変換する。"""
        ...


class EventReactionCandidatePresenter(Protocol):
    """ReactionCandidateをPresentedOutputに変換するプロトコル。"""

    def present(self, candidate: ReactionCandidate) -> PresentedOutput:
        """リアクション候補を提示可能な出力へ変換する。"""
        ...
