"""Iris 観測のための、トランスポート非依存ランタイムサービス境界。"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import TYPE_CHECKING, Protocol

from iris.contracts.actions import PresentedOutput
from iris.contracts.learning import RuntimeLearningEvent, RuntimeLearningEventKind
from iris.core.datetime_utils import now_utc
from iris.runtime.ingress.observation_ingress import (
    ObservationCapability,
    trusted_adapter_ingress,
    unauthenticated_external_ingress,
)
from iris.runtime.observability.context import RuntimeTraceContext, bind_trace_context, trace_extra
from iris.runtime.observation_router import (
    ActivityEventRoute,
    PresenceSignalRoute,
    UserFeedbackRoute,
    route_observation,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import datetime

    from iris.contracts.delivery import DeliveryRouteHint
    from iris.contracts.observations import ActivityEventObservation, Observation
    from iris.contracts.workspace_context import SituationContextSnapshot
    from iris.core.ids import CorrelationId
    from iris.runtime.app import IrisApp
    from iris.runtime.ingress.observation_ingress import ObservationIngressContext
    from iris.runtime.ingress.observation_integrator import ObservationIntegrator
    from iris.runtime.observability.context import RuntimeLogValue
    from iris.runtime.observability.ports import RuntimeObservationObserver


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
        capabilities: frozenset[ObservationCapability] | set[ObservationCapability],
        correlation_id: CorrelationId | None = None,
        delivery_route: DeliveryRouteHint | None = None,
    ) -> ObservationEnvelope:
        """信頼済みadapter observation用のcapability付きenvelopeを作成する。

        Args:
            observation: Observation。
            adapter_id: 信頼済みadapterの識別子。
            provider: 任意的なprovider名。
            capabilities: 付与するcapability。呼び出し側が明示的に指定する必要がある。
            correlation_id: 任意的なcorrelation ID。
            delivery_route: 任意的な配送 route hint。

        Returns:
            認証済みingressを持つObservationEnvelope。
        """
        return cls(
            observation=observation,
            ingress=trusted_adapter_ingress(
                adapter_id=adapter_id,
                provider=provider,
                capabilities=capabilities,
                delivery_route=delivery_route,
            ),
            correlation_id=correlation_id,
        )


@dataclass(frozen=True)
class RuntimeResponse:
    """IrisRuntimeService が返すトランスポート非依存の結果。"""

    output: PresentedOutput
    correlation_id: CorrelationId | None = None


@dataclass(frozen=True)
class RuntimeServiceExtensions:
    """RuntimeServiceへ注入する任意の副作用境界。"""

    observation_observer: RuntimeObservationObserver | None = None
    conversation_runtime: ConversationTurnRuntime | None = None
    runtime_learning_hook_runner: RuntimeLearningEventRunner | None = None


class ObservationRuntimeService(Protocol):
    """観測を処理して RuntimeResponse を返す runtime 境界 port。

    SchedulerRunner など runtime orchestration はこの port に依存し、
    具象 IrisRuntimeService に直接結合しない。
    """

    async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
        """観測を処理し、出力と correlation id を返す。

        Returns:
            RuntimeResponse: PresentedOutput と保持された correlation ID。
        """
        ...


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


class ConversationTurnRuntime(Protocol):
    """Cognitive route前後の短期会話context境界。"""

    async def load_context(
        self,
        observation: Observation,
        base: SituationContextSnapshot | None,
    ) -> SituationContextSnapshot:
        """過去会話を状況contextへ追加する。"""
        ...

    async def record_response(
        self,
        observation: Observation,
        output: PresentedOutput,
    ) -> None:
        """成功したsendable turnを記録する。"""
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


class RuntimeLearningEventRunner(Protocol):
    """Runtime outcome学習イベントを副作用境界へ渡すrunner。"""

    async def run(self, event: RuntimeLearningEvent) -> None:
        """Runtime learning eventを処理する。"""
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
        extensions: RuntimeServiceExtensions | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        """明示的に注入されたappとoptional observation pipelineでserviceを生成する。"""
        runtime_extensions = extensions or RuntimeServiceExtensions()
        self._app = app
        self._observation_pipeline = observation_pipeline
        self._workspace_context_assembler = workspace_context_assembler
        self._activity_event_reaction_handler = activity_event_reaction_handler
        self._observation_observer = runtime_extensions.observation_observer
        self._conversation_runtime = runtime_extensions.conversation_runtime
        self._runtime_learning_hook_runner = runtime_extensions.runtime_learning_hook_runner
        self._now = now or now_utc

    async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
        """State integration後、必要な観測だけをIrisApp経由で処理する。

        Returns:
            RuntimeResponse: PresentedOutput と保持された correlation ID。
        """
        started_at = time.perf_counter()
        trace_context = _trace_context_from_envelope(envelope)
        with bind_trace_context(trace_context):
            try:
                return await self._handle_observation_bound(envelope, started_at)
            except Exception as exc:
                self._record(
                    "runtime.observation.error",
                    latency_ms=_latency_ms(started_at),
                    error_type=type(exc).__name__,
                )
                raise

    async def _handle_observation_bound(
        self,
        envelope: ObservationEnvelope,
        started_at: float,
    ) -> RuntimeResponse:
        """束縛済み trace context 内で観測を処理する。

        Returns:
            観測処理結果。
        """
        observation = envelope.observation
        self._record("runtime.observation.start")

        self._record("runtime.observation.integrate.start")
        await self._run_integrators(observation, envelope.ingress)
        self._record("runtime.observation.integrate.success")

        self._record("runtime.context.assemble.start")
        situation_context = await self._assemble_situation_context(observation)
        self._record("runtime.context.assemble.success")

        route = route_observation(observation)
        route_name = _route_name(route)
        self._record("runtime.observation.route", route=route_name)
        if isinstance(route, ActivityEventRoute):
            return await self._handle_activity_event(
                route.observation,
                situation_context,
                envelope.ingress,
                envelope.correlation_id,
                started_at,
            )

        if isinstance(route, PresenceSignalRoute):
            self._record(
                "runtime.observation.no_send",
                route=route_name,
                output_present=False,
            )
            response = RuntimeResponse(
                output=PresentedOutput(text=None),
                correlation_id=envelope.correlation_id,
            )
            self._record(
                "runtime.observation.success",
                route=route_name,
                latency_ms=_latency_ms(started_at),
                output_present=response.output.is_sendable,
            )
            return response

        if isinstance(route, UserFeedbackRoute):
            return await self._handle_user_feedback(
                route.observation,
                envelope.correlation_id,
                started_at,
            )

        self._record("runtime.cognitive.start", route=route_name)
        situation_context = await self._load_conversation_context(
            route.observation,
            situation_context,
        )
        output = await self._app.process_observation(
            route.observation,
            situation_context=situation_context,
        )
        self._record(
            "runtime.cognitive.success",
            route=route_name,
            output_present=output.is_sendable,
        )
        await self._record_conversation_response(route.observation, output)
        await self._run_runtime_learning_event(
            kind=_runtime_learning_event_kind(output),
            observation=route.observation,
            output=output,
            route=route_name,
        )
        self._record(
            "runtime.observation.success",
            route=route_name,
            latency_ms=_latency_ms(started_at),
            output_present=output.is_sendable,
        )
        return RuntimeResponse(output=output, correlation_id=envelope.correlation_id)

    async def _load_conversation_context(
        self,
        observation: Observation,
        situation_context: SituationContextSnapshot | None,
    ) -> SituationContextSnapshot | None:
        """Optional conversation runtimeから直近会話を取得する。

        Returns:
            会話windowを含む状況context。未配線時は元のcontext。
        """
        if self._conversation_runtime is None:
            return situation_context
        return await self._conversation_runtime.load_context(observation, situation_context)

    async def _record_conversation_response(
        self,
        observation: Observation,
        output: PresentedOutput,
    ) -> None:
        """Optional conversation runtimeへ成功出力を渡す。"""
        if self._conversation_runtime is not None:
            await self._conversation_runtime.record_response(observation, output)

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
        started_at: float,
    ) -> RuntimeResponse:
        """ActivityEventObservationに対し、event reaction handlerに委譲する。

        Returns:
            RuntimeResponse: event reactionまたはno-sendの結果。
        """
        if self._activity_event_reaction_handler is not None:
            self._record("runtime.activity_reaction.start", route="activity_event")
            output = await self._activity_event_reaction_handler.handle(
                observation,
                situation_context,
                ingress,
            )
            self._record(
                "runtime.activity_reaction.success",
                route="activity_event",
                output_present=output.is_sendable,
            )
        else:
            output = PresentedOutput(text=None)
        if not output.is_sendable:
            self._record(
                "runtime.observation.no_send",
                route="activity_event",
                output_present=False,
            )
        await self._run_runtime_learning_event(
            kind=_runtime_learning_event_kind(output),
            observation=observation,
            output=output,
            route="activity_event",
        )
        self._record(
            "runtime.observation.success",
            route="activity_event",
            latency_ms=_latency_ms(started_at),
            output_present=output.is_sendable,
        )
        return RuntimeResponse(output=output, correlation_id=correlation_id)

    async def _handle_user_feedback(
        self,
        observation: Observation,
        correlation_id: CorrelationId | None,
        started_at: float,
    ) -> RuntimeResponse:
        """UserFeedbackObservationを認知cycleに流さずruntime学習境界へ渡す。

        Returns:
            RuntimeResponse: no-sendの結果。
        """
        await self._run_runtime_learning_event(
            kind=RuntimeLearningEventKind.USER_FEEDBACK,
            observation=observation,
            output=None,
            route="user_feedback",
        )
        self._record(
            "runtime.observation.no_send",
            route="user_feedback",
            output_present=False,
        )
        response = RuntimeResponse(output=PresentedOutput(text=None), correlation_id=correlation_id)
        self._record(
            "runtime.observation.success",
            route="user_feedback",
            latency_ms=_latency_ms(started_at),
            output_present=False,
        )
        return response

    async def _run_runtime_learning_event(
        self,
        *,
        kind: RuntimeLearningEventKind,
        observation: Observation,
        output: PresentedOutput | None,
        route: str,
    ) -> None:
        """任意配線されたruntime学習フックへpost-result eventを渡す。"""
        if self._runtime_learning_hook_runner is None:
            return
        await self._runtime_learning_hook_runner.run(
            RuntimeLearningEvent(
                kind=kind,
                observation=observation,
                output=output,
                occurred_at=self._now(),
                route=route,
                source_observation_id=observation.observation_id,
            )
        )

    def _record(self, event: str, **fields: RuntimeLogValue) -> None:
        """Optional observer へ runtime event を渡す。"""
        if self._observation_observer is not None:
            self._observation_observer.record(event, **trace_extra(**fields))


def _trace_context_from_envelope(
    envelope: ObservationEnvelope,
) -> RuntimeTraceContext:
    """ObservationEnvelope から安全な trace context を生成する。

    Returns:
        request scope に束縛する trace context。
    """
    observation = envelope.observation
    context = observation.context
    actor_id = context.actor_id
    space_id = context.space_id
    return RuntimeTraceContext(
        correlation_id=str(envelope.correlation_id or observation.observation_id),
        observation_id=str(observation.observation_id),
        observation_kind=observation.kind.value,
        ingress_kind=_ingress_kind(envelope.ingress),
        adapter_id=envelope.ingress.adapter_id,
        provider=envelope.ingress.provider,
        actor_id=str(actor_id) if actor_id is not None else None,
        space_id=str(space_id) if space_id is not None else None,
    )


def _ingress_kind(ingress: ObservationIngressContext) -> str:
    """Ingress metadata から安定した種別名を返す。

    Returns:
        安定した ingress 種別名。
    """
    if ingress.authenticated:
        return "trusted_adapter"
    return "external_client"


def _route_name(
    route: ActivityEventRoute | PresenceSignalRoute | UserFeedbackRoute | object,
) -> str:
    """Runtime route から安全な route 名を返す。

    Returns:
        安全な route 名。
    """
    if isinstance(route, ActivityEventRoute):
        return "activity_event"
    if isinstance(route, PresenceSignalRoute):
        return "presence_signal"
    if isinstance(route, UserFeedbackRoute):
        return "user_feedback"
    return "cognitive"


def _runtime_learning_event_kind(output: PresentedOutput) -> RuntimeLearningEventKind:
    """出力可能性からruntime学習イベント種別を返す。

    Returns:
        sendable outputならinline response、それ以外はno-action。
    """
    if output.is_sendable:
        return RuntimeLearningEventKind.INLINE_RESPONSE_GENERATED
    return RuntimeLearningEventKind.NO_ACTION


def _latency_ms(started_at: float) -> float:
    """開始時刻からの経過時間をミリ秒で返す。

    Returns:
        経過時間ミリ秒。
    """
    return (time.perf_counter() - started_at) * 1000.0
