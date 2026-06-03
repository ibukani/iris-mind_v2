from typing import Protocol

from iris.contracts.actions import PresentedOutput
from iris.safety.action_gate import GateDecision, SafetyDecision


class OutputSafetyGate(Protocol):
    async def check_output(self, output: PresentedOutput) -> SafetyDecision: ...


class AllowAllOutputGate:
    async def check_output(self, output: PresentedOutput) -> SafetyDecision:
        return SafetyDecision(decision=GateDecision.ALLOW)
