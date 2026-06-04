"""Action safety gate protocol and pass-through implementations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from iris.contracts.actions import ActionPlan


class GateDecision(StrEnum):
    """Enumeration of possible gate decisions."""

    ALLOW = "allow"
    BLOCK = "block"


@dataclass(frozen=True)
class SafetyDecision:
    """Result of a safety gate check."""

    decision: GateDecision
    reason: str | None = None


class ActionSafetyGate(Protocol):
    """Protocol for gates that inspect and potentially block action plans."""

    async def check_plan(self, plan: ActionPlan) -> SafetyDecision:
        """Evaluate an action plan and return a safety decision."""
        ...


class AllowAllActionGate:
    """Pass-through action gate that allows every plan."""

    async def check_plan(self, plan: ActionPlan) -> SafetyDecision:
        """Allow all action plans unconditionally.

        Args:
            plan: The action plan to check.

        Returns:
            A SafetyDecision with decision ALLOW.
        """
        return SafetyDecision(decision=GateDecision.ALLOW)
