"""Iris 観測のための、トランスポート非依存ランタイムサービス境界。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.actions import PresentedOutput
from iris.contracts.observations import (
    ActivityEventObservation,
    PresenceSignalObservation,
)
from iris.runtime.observations.ingress import unauthenticated_external_ingress
from iris.runtime.observations.trust import ObservationTrustPolicy
from iris.safety.action_gate import GateDecision
from iris.safety.output_filter import AllowAllOutputGate

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import SituationContextSnapshot
    from iris.contracts.observations import Observation
    from iris.core.ids import CorrelationId
    from iris.runtime.activity.integrator import ActivityIntegrator
    from iris.runtime.app import IrisApp
    from iris.runtime.context.workspace_assembler import WorkspaceContextAssembler
    from iris.runtime.event_reaction.runner import EventReactionRunner
    from iris.runtime.observations.ingress import ObservationIngressContext
    from iris.runtime.presence.integrator import PresenceIntegrator
    from iris.runtime.spaces.occupancy_integrator import SpaceOccupancyIntegrator
    from iris.safety.output_filter import OutputSafetyGate


@dataclass(frozen=True)
class RuntimeIntegrators:
    """Activity / presence / occupancy 統合のoptional bundle。"""

    activity: ActivityIntegrator | None = None
    presence: PresenceIntegrator | None = None
    occupancy: SpaceOccupancyIntegrator | None = None


@dataclass(frozen=True)
class ObservationEnvelope:
    """受信観測を入れるトランスポート非依存コンテナ。"""

    observation: Observation
    ingress: ObservationIngressContext
    correlation_id: CorrelationId | None = None

    @classmethod
    def external_client(
        cls,
        *,
        observation: Observation,
        correlation_id: CorrelationId | None = None,
    ) -> ObservationEnvelope:
        """外部client request用のcapabilityなしenvelopeを作成する。

        Returns:
            未認証ingressを持つObservationEnvelope。
        """
        return cls(
            observation=observation,
            ingress=unauthenticated_external_ingress(),
            correlation_id=correlation_id,
        )


@dataclass(frozen=True)
class RuntimeResponse:
    """IrisRuntimeService が返すトランスポート非依存の結果。"""

    output: PresentedOutput
    correlation_id: CorrelationId | None = None


class IrisRuntimeService:
    """観測stateを統合し、sendable観測だけをIrisAppへ委譲するruntime境界。"""

    def __init__(
        self,
        app: IrisApp,
        *,
        integrators: RuntimeIntegrators | None = None,
        workspace_context_assembler: WorkspaceContextAssembler | None = None,
        event_reaction_runner: EventReactionRunner | None = None,
        trust_policy: ObservationTrustPolicy | None = None,
        event_reaction_output_gate: OutputSafetyGate | None = None,
    ) -> None:
        """明示的に注入されたappとoptional integratorでserviceを生成する。"""
        self._app = app
        self._integrators = integrators or RuntimeIntegrators()
        self._workspace_context_assembler = workspace_context_assembler
        self._event_reaction_runner = event_reaction_runner
        self._trust_policy = trust_policy or ObservationTrustPolicy()
        self._event_reaction_output_gate = event_reaction_output_gate or AllowAllOutputGate()

    async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
        """State integration後、必要な観測だけをIrisApp経由で処理する。

        Returns:
            RuntimeResponse: PresentedOutput と保持された correlation ID。
        """
        observation = envelope.observation
        await self._run_integrators(observation, envelope.ingress)
        situation_context = await self._assemble_situation_context(observation)

        if isinstance(observation, ActivityEventObservation):
            return await self._handle_activity_event(
                observation,
                situation_context,
                envelope.ingress,
                envelope.correlation_id,
            )

        if isinstance(observation, PresenceSignalObservation):
            return RuntimeResponse(
                output=PresentedOutput(text=None),
                correlation_id=envelope.correlation_id,
            )

        output = await self._app.process_observation(
            observation,
            situation_context=situation_context,
        )
        return RuntimeResponse(output=output, correlation_id=envelope.correlation_id)

    async def _run_integrators(
        self,
        observation: Observation,
        ingress: ObservationIngressContext,
    ) -> None:
        """Optionalなintegratorを観測に適用する。"""
        if self._integrators.activity is not None:
            await self._integrators.activity.integrate_observation(observation, ingress)
        if self._integrators.presence is not None:
            await self._integrators.presence.integrate_observation(observation, ingress)
        if self._integrators.occupancy is not None:
            await self._integrators.occupancy.integrate_observation(observation, ingress)

    async def _assemble_situation_context(
        self,
        observation: Observation,
    ) -> SituationContextSnapshot | None:
        """WorkspaceContextAssemblerがあれば状況スナップショットを組み立てる。

        Returns:
            SituationContextSnapshot | None: 組み立てた状況スナップショット、またはNone。
        """
        if self._workspace_context_assembler is None:
            return None
        return await self._workspace_context_assembler.assemble(observation)

    async def _handle_activity_event(
        self,
        observation: ActivityEventObservation,
        situation_context: SituationContextSnapshot | None,
        ingress: ObservationIngressContext,
        correlation_id: CorrelationId | None,
    ) -> RuntimeResponse:
        """ActivityEventObservationに対し、event reactionがあれば返す。

        Returns:
            RuntimeResponse: event reactionまたはno-sendの結果。
        """
        output: PresentedOutput | None = None
        if (
            situation_context is not None
            and self._event_reaction_runner is not None
            and self._trust_policy.can_react_to_activity_event(ingress)
        ):
            output = await self._event_reaction_runner.react(
                observation,
                situation_context=situation_context,
            )

        if output is not None and output.is_sendable:
            output = await self._filter_event_reaction_output(output)

        if output is None:
            output = PresentedOutput(text=None)
        return RuntimeResponse(output=output, correlation_id=correlation_id)

    async def _filter_event_reaction_output(
        self,
        output: PresentedOutput,
    ) -> PresentedOutput:
        """Event reaction出力をoutput safety gateで検査する。

        Returns:
            PresentedOutput: gate通過後のoutput、またはブロック時はno-send。
        """
        decision = await self._event_reaction_output_gate.check_output(output)
        if decision.decision is GateDecision.BLOCK:
            return PresentedOutput(text=None)
        return output
