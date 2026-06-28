"""Presentation suite."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.presentation.ports import ActionPlanPresenter, EventReactionCandidatePresenter


@dataclass(frozen=True)
class PresentationSuite:
    """Centralized presentation boundary."""

    action_plan_presenter: ActionPlanPresenter
    event_reaction_presenter: EventReactionCandidatePresenter
