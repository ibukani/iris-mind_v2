"""ActivityEventObservation の event reaction パイプラインを担当する handler。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.actions import PresentedOutput
from iris.safety.action_gate import GateDecision

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import SituationContextSnapshot
    from iris.contracts.observations import ActivityEventObservation
    from iris.runtime.ingress.activity_event_reaction_runner import EventReactionRunner
    from iris.runtime.ingress.observation_ingress import ObservationIngressContext
    from iris.runtime.ingress.observation_trust import ObservationTrustPolicy
    from iris.safety.output_filter import OutputSafetyGate


@dataclass(frozen=True)
class ActivityEventReactionHandler:
    """ActivityEventObservation に対する trust check → reaction → output gate パイプライン。"""

    trust_policy: ObservationTrustPolicy
    runner: EventReactionRunner
    output_gate: OutputSafetyGate

    async def handle(
        self,
        observation: ActivityEventObservation,
        situation_context: SituationContextSnapshot | None,
        ingress: ObservationIngressContext,
    ) -> PresentedOutput:
        """Trust check → reaction → output gate → fallback。

        Args:
            observation: 処理対象の activity event observation。
            situation_context: ランタイムから組み立てられた状況スナップショット。
            ingress: 観測の ingress context。

        Returns:
            PresentedOutput: reaction 出力、または no-send。
        """
        output: PresentedOutput | None = None
        if situation_context is not None and self.trust_policy.can_react_to_activity_event(ingress):
            output = await self.runner.react(
                observation,
                situation_context=situation_context,
            )

        if output is not None and output.is_sendable:
            output = await self._filter_output(output)

        return output or PresentedOutput(text=None)

    async def _filter_output(self, output: PresentedOutput) -> PresentedOutput:
        """Event reaction 出力を output safety gate で検査する。

        Returns:
            PresentedOutput: gate 通過後の output、またはブロック時は no-send。
        """
        decision = await self.output_gate.check_output(output)
        if decision.decision is GateDecision.BLOCK:
            return PresentedOutput(text=None)
        return output
