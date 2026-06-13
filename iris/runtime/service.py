"""Iris 観測のための、トランスポート非依存ランタイムサービス境界。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.actions import PresentedOutput
from iris.contracts.observations import (
    ActivityEventObservation,
    PresenceSignalObservation,
)
from iris.runtime.observations.ingress import (
    ObservationCapability,
    trusted_adapter_ingress,
    unauthenticated_external_ingress,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.cognitive.workspace.frame import SituationContextSnapshot
    from iris.contracts.observations import Observation
    from iris.core.ids import CorrelationId
    from iris.runtime.app import IrisApp
    from iris.runtime.context.workspace_assembler import WorkspaceContextAssembler
    from iris.runtime.event_reaction.handler import ActivityEventReactionHandler
    from iris.runtime.observations.ingress import ObservationIngressContext
    from iris.runtime.observations.integrator import ObservationIntegrator


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

    @classmethod
    def trusted_adapter(
        cls,
        *,
        observation: Observation,
        adapter_id: str,
        provider: str | None = None,
        capabilities: frozenset[ObservationCapability] | None = None,
        correlation_id: CorrelationId | None = None,
    ) -> ObservationEnvelope:
        """信頼済みadapter observation用のcapability付きenvelopeを作成する。

        Args:
            observation: Observation。
            adapter_id: 信頼済みadapterの識別子。
            provider: 任意的なprovider名。
            capabilities: 付与するcapability。デフォルトは全capability。
            correlation_id: 任意的なcorrelation ID。

        Returns:
            認証済みingressを持つObservationEnvelope。
        """
        return cls(
            observation=observation,
            ingress=trusted_adapter_ingress(
                adapter_id=adapter_id,
                provider=provider,
                capabilities=capabilities or frozenset(ObservationCapability),
            ),
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
        integrators: Sequence[ObservationIntegrator] | None = None,
        workspace_context_assembler: WorkspaceContextAssembler | None = None,
        activity_event_reaction_handler: ActivityEventReactionHandler | None = None,
    ) -> None:
        """明示的に注入されたappとoptional integratorでserviceを生成する。"""
        self._app = app
        self._integrators: Sequence[ObservationIntegrator] = tuple(integrators or ())
        self._workspace_context_assembler = workspace_context_assembler
        self._activity_event_reaction_handler = activity_event_reaction_handler

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
        for integrator in self._integrators:
            await integrator.integrate_observation(observation, ingress)

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
        """ActivityEventObservationに対し、event reaction handlerに委譲する。

        Returns:
            RuntimeResponse: event reactionまたはno-sendの結果。
        """
        if self._activity_event_reaction_handler is not None:
            output = await self._activity_event_reaction_handler.handle(
                observation,
                situation_context,
                ingress,
            )
        else:
            output = PresentedOutput(text=None)
        return RuntimeResponse(output=output, correlation_id=correlation_id)
