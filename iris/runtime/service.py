"""Iris 観測のための、トランスポート非依存ランタイムサービス境界。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.core.datetime_utils import now_utc
from iris.runtime.model_call_budget import bind_model_call_budget_scope
from iris.runtime.observability.context import RuntimeTraceContext, bind_trace_context
from iris.runtime.observability.ports import RuntimeLatencyStage
from iris.runtime.observability.runtime_observation import RuntimeObservationTelemetry
from iris.runtime.observability.timing import latency_ms, perf_counter
from iris.runtime.observation_processor import RuntimeObservationProcessor
from iris.runtime.service_contracts import (
    ActivityEventReactionPipeline,
    ConversationTurnRuntime,
    IntegratingObservationPipeline,
    ObservationEnvelope,
    ObservationProcessingPipeline,
    ObservationRuntimeService,
    RuntimeLearningEventRunner,
    RuntimeResponse,
    RuntimeServiceExtensions,
    WorkspaceContextProvider,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from iris.runtime.app import IrisApp
    from iris.runtime.ingress.observation_ingress import ObservationIngressContext

__all__ = [
    "ActivityEventReactionPipeline",
    "ConversationTurnRuntime",
    "IntegratingObservationPipeline",
    "IrisRuntimeService",
    "ObservationEnvelope",
    "ObservationProcessingPipeline",
    "ObservationRuntimeService",
    "RuntimeLearningEventRunner",
    "RuntimeResponse",
    "RuntimeServiceExtensions",
    "WorkspaceContextProvider",
]


class IrisRuntimeService:
    """Trace scope と runtime observation processor を束ねる service 境界。"""

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
        """明示依存から transport-independent runtime service を生成する。"""
        runtime_extensions = extensions or RuntimeServiceExtensions()
        self._app = app
        self._telemetry = RuntimeObservationTelemetry(
            runtime_extensions.observation_observer,
            runtime_extensions.latency_budget,
        )
        self._processor = RuntimeObservationProcessor(
            app=app,
            telemetry=self._telemetry,
            observation_pipeline=observation_pipeline,
            workspace_context_assembler=workspace_context_assembler,
            activity_event_reaction_handler=activity_event_reaction_handler,
            conversation_runtime=runtime_extensions.conversation_runtime,
            runtime_learning_hook_runner=runtime_extensions.runtime_learning_hook_runner,
            now=now or now_utc,
        )

    async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
        """Observation を trace scope 内で処理する。

        Returns:
            PresentedOutput と保持された correlation ID。
        """
        started_at = perf_counter()
        trace_context = _trace_context_from_envelope(envelope)
        with bind_trace_context(trace_context), bind_model_call_budget_scope():
            try:
                output = await self._processor.process(
                    envelope.observation,
                    envelope.ingress,
                    started_at=started_at,
                )
            except Exception as exc:
                self._telemetry.record_stage(
                    RuntimeLatencyStage.HANDLE_OBSERVATION,
                    started_at,
                    error_type=type(exc).__name__,
                )
                self._telemetry.record(
                    "runtime.observation.error",
                    latency_ms=latency_ms(started_at),
                    error_type=type(exc).__name__,
                )
                raise
            self._telemetry.record_stage(
                RuntimeLatencyStage.HANDLE_OBSERVATION,
                started_at,
                output_present=output.is_sendable,
            )
            return RuntimeResponse(output=output, correlation_id=envelope.correlation_id)


def _trace_context_from_envelope(envelope: ObservationEnvelope) -> RuntimeTraceContext:
    """ObservationEnvelope から安全な trace context を生成する。

    Returns:
        Request scope に束縛する trace context。
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
