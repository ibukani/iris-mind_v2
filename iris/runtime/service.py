"""Iris 観測のための、トランスポート非依存ランタイムサービス境界。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from iris.contracts.actions import PresentedOutput
from iris.runtime.observation_router import (
    ActivityEventRoute,
    PresenceSignalRoute,
    route_observation,
)
from iris.runtime.observations.ingress import (
    ObservationCapability,
    trusted_adapter_ingress,
    unauthenticated_external_ingress,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.cognitive.workspace.frame import SituationContextSnapshot
    from iris.contracts.observations import ActivityEventObservation, Observation
    from iris.core.ids import CorrelationId
    from iris.runtime.app import IrisApp
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


class ObservationProcessingPipeline(Protocol):
    """RuntimeService の observation 統合境界。"""

    async def integrate_observation(
        self,
        observation: Observation,
        ingress: ObservationIngressContext,
    ) -> None:
        """Observation claim を runtime state へ統合する。"""
        ...


class WorkspaceContextProvider(Protocol):
    """RuntimeService に状況 context を供給する境界。"""

    async def assemble(self, observation: Observation) -> SituationContextSnapshot | None:
        """Observation から workspace context を組み立てる。"""
        ...


class ActivityEventReactionPipeline(Protocol):
    """Activity event reaction の runtime 境界。"""

    async def handle(
        self,
        observation: ActivityEventObservation,
        situation_context: SituationContextSnapshot | None,
        ingress: ObservationIngressContext,
    ) -> PresentedOutput:
        """Activity event に対する reaction output を返す。"""
        ...


@dataclass(frozen=True)
class IntegratingObservationPipeline:
    """複数の observation integrator を一つの runtime 境界として実行する。"""

    integrators: Sequence[ObservationIntegrator]

    async def integrate_observation(
        self,
        observation: Observation,
        ingress: ObservationIngressContext,
    ) -> None:
        """登録された integrator を順に実行する。"""
        for integrator in self.integrators:
            await integrator.integrate_observation(observation, ingress)


class IrisRuntimeService:
    """観測stateを統合し、sendable観測だけをIrisAppへ委譲するruntime境界。"""

    def __init__(
        self,
        app: IrisApp,
        *,
        observation_pipeline: ObservationProcessingPipeline | None = None,
        workspace_context_assembler: WorkspaceContextProvider | None = None,
        activity_event_reaction_handler: ActivityEventReactionPipeline | None = None,
    ) -> None:
        """明示的に注入されたappとoptional observation pipelineでserviceを生成する。"""
        self._app = app
        self._observation_pipeline = observation_pipeline
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

        route = route_observation(observation)
        if isinstance(route, ActivityEventRoute):
            return await self._handle_activity_event(
                route.observation,
                situation_context,
                envelope.ingress,
                envelope.correlation_id,
            )

        if isinstance(route, PresenceSignalRoute):
            return RuntimeResponse(
                output=PresentedOutput(text=None),
                correlation_id=envelope.correlation_id,
            )

        output = await self._app.process_observation(
            route.observation,
            situation_context=situation_context,
        )
        return RuntimeResponse(output=output, correlation_id=envelope.correlation_id)

    async def _run_integrators(
        self,
        observation: Observation,
        ingress: ObservationIngressContext,
    ) -> None:
        """Optionalなobservation pipelineを観測に適用する。"""
        if self._observation_pipeline is not None:
            await self._observation_pipeline.integrate_observation(observation, ingress)

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
