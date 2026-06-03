from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from iris.contracts.actions import ActionPlan


class GateDecision(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"


@dataclass(frozen=True)
class SafetyDecision:
    decision: GateDecision
    reason: str | None = None


class ActionSafetyGate(Protocol):
    async def check_plan(self, plan: ActionPlan) -> SafetyDecision: ...


class AllowAllActionGate:
    async def check_plan(self, plan: ActionPlan) -> SafetyDecision:
        return SafetyDecision(decision=GateDecision.ALLOW)
