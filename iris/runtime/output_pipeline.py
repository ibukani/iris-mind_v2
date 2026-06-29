"""ランタイムの出力パイプライン。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.actions import PresentedOutput
from iris.safety.action_gate import GateDecision

if TYPE_CHECKING:
    from iris.contracts.actions import ActionPlan
    from iris.presentation.suite import PresentationSuite
    from iris.safety.action_gate import ActionSafetyGate
    from iris.safety.output_filter import OutputSafetyGate


@dataclass(frozen=True)
class RuntimeOutputPipeline:
    """アクションとリアクションの出力パイプライン（SafetyとPresentation）。"""

    presentation: PresentationSuite
    action_safety_gate: ActionSafetyGate
    output_safety_gate: OutputSafetyGate

    async def present_action_plan(self, plan: ActionPlan) -> PresentedOutput:
        """ActionPlanを検証・フォーマットし、PresentedOutputとして返す。

        Args:
            plan: 提案されたActionPlan。

        Returns:
            PresentedOutput: 出力、またはブロック時はno-send。
        """
        # 1. Action Safety
        action_decision = await self.action_safety_gate.check_plan(plan)
        if action_decision.decision is GateDecision.BLOCK:
            return PresentedOutput(text=None)

        # 2. Presentation
        output = await self.presentation.present_action_plan(plan)

        # 3. Output Safety
        if output.is_sendable:
            out_decision = await self.output_safety_gate.check_output(output)
            if out_decision.decision is GateDecision.BLOCK:
                return PresentedOutput(text=None)

        return output
