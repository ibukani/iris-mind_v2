"""Output safety gate protocol and pass-through implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from iris.safety.action_gate import GateDecision, SafetyDecision

if TYPE_CHECKING:
    from iris.contracts.actions import PresentedOutput


class OutputSafetyGate(Protocol):
    """Protocol for gates that inspect and potentially block presented output."""

    async def check_output(self, output: PresentedOutput) -> SafetyDecision:
        """Evaluate presented output and return a safety decision."""
        ...


class AllowAllOutputGate:
    """Pass-through output gate that allows every output."""

    async def check_output(self, output: PresentedOutput) -> SafetyDecision:  # noqa: PLR6301, ARG002
        """Allow all output unconditionally.

        Args:
            output: The presented output to check.

        Returns:
            A SafetyDecision with decision ALLOW.
        """
        return SafetyDecision(decision=GateDecision.ALLOW)
