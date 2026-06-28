"""Presentation ports."""

from __future__ import annotations

from typing import Protocol

from iris.contracts.actions import ActionPlan, PresentedOutput
from iris.contracts.event_reaction import ReactionCandidate


class ActionPlanPresenter(Protocol):
    """ActionPlanをPresentedOutputに変換するプロトコル。"""

    async def present(self, plan: ActionPlan) -> PresentedOutput:
        ...


class EventReactionCandidatePresenter(Protocol):
    """ReactionCandidateをPresentedOutputに変換するプロトコル。"""

    def present(self, candidate: ReactionCandidate) -> PresentedOutput:
        ...
