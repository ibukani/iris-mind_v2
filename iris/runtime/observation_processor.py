"""Runtime observation の統合、routing、reaction、cognitive 実行。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.actions import PresentedOutput
from iris.contracts.learning import RuntimeLearningEvent, RuntimeLearningEventKind
from iris.contracts.model_policy import ModelCallSite
from iris.core.datetime_utils import now_utc
from iris.runtime.model_call_budget import bind_model_call_site
from iris.runtime.observability.ports import RuntimeLatencyStage
from iris.runtime.observability.timing import latency_ms, perf_counter
from iris.runtime.observation_router import (
    ActivityEventRoute,
    PresenceSignalRoute,
    UserFeedbackRoute,
    route_observation,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from iris.contracts.observations import ActivityEventObservation, Observation
    from iris.contracts.workspace_context import SituationContextSnapshot
    from iris.runtime.app import IrisApp
    from iris.runtime.ingress.observation_ingress import ObservationIngressContext
    from iris.runtime.observability.runtime_observation import RuntimeObservationTelemetry
    from iris.runtime.service_contracts import (
        ActivityEventReactionPipeline,
        ConversationTurnRuntime,
        ObservationProcessingPipeline,
        RuntimeLearningEventRunner,
        WorkspaceContextProvider,
    )


@dataclass(frozen=True)
class RuntimeObservationProcessor:
    """Observation の runtime-side effect と route 実行を担当する。"""

    app: IrisApp
    telemetry: RuntimeObservationTelemetry
    observation_pipeline: ObservationProcessingPipeline | None = None
    workspace_context_assembler: WorkspaceContextProvider | None = None
    activity_event_reaction_handler: ActivityEventReactionPipeline | None = None
    conversation_runtime: ConversationTurnRuntime | None = None
    runtime_learning_hook_runner: RuntimeLearningEventRunner | None = None
    now: Callable[[], datetime] = now_utc

    async def process(
        self,
        observation: Observation,
        ingress: ObservationIngressContext,
        *,
        started_at: float,
    ) -> PresentedOutput:
        """Observation を統合し、route に応じた output を返す。

        Returns:
            Route 実行で得た PresentedOutput。
        """
        self.telemetry.record("runtime.observation.start")
        await self._integrate_observation(observation, ingress)
        situation_context = await self._assemble_context(observation)

        route = route_observation(observation)
        route_name = _route_name(route)
        self.telemetry.record("runtime.observation.route", route=route_name)
        if isinstance(route, ActivityEventRoute):
            return await self._handle_activity_event(
                route.observation,
                situation_context,
                ingress,
                started_at,
            )
        if isinstance(route, PresenceSignalRoute):
            return self._complete_observation(
                PresentedOutput(text=None),
                route=route_name,
                started_at=started_at,
                record_no_send=True,
            )
        if isinstance(route, UserFeedbackRoute):
            return await self._handle_user_feedback(route.observation, started_at)
        return await self._handle_cognitive_route(
            route.observation,
            situation_context,
            route_name,
            started_at,
        )

    async def _integrate_observation(
        self,
        observation: Observation,
        ingress: ObservationIngressContext,
    ) -> None:
        self.telemetry.record("runtime.observation.integrate.start")
        stage_started_at = perf_counter()
        if self.observation_pipeline is not None:
            await self.observation_pipeline.integrate_observation(observation, ingress)
        self.telemetry.record_stage(
            RuntimeLatencyStage.OBSERVATION_INTEGRATION,
            stage_started_at,
        )
        self.telemetry.record("runtime.observation.integrate.success")

    async def _assemble_context(
        self,
        observation: Observation,
    ) -> SituationContextSnapshot | None:
        self.telemetry.record("runtime.context.assemble.start")
        stage_started_at = perf_counter()
        context = None
        if self.workspace_context_assembler is not None:
            context = await self.workspace_context_assembler.assemble(observation)
        self.telemetry.record_stage(
            RuntimeLatencyStage.WORKSPACE_CONTEXT_ASSEMBLY,
            stage_started_at,
        )
        self.telemetry.record("runtime.context.assemble.success")
        return context

    async def _handle_cognitive_route(
        self,
        observation: Observation,
        situation_context: SituationContextSnapshot | None,
        route: str,
        started_at: float,
    ) -> PresentedOutput:
        self.telemetry.record("runtime.cognitive.start", route=route)
        situation_context = await self._load_conversation_context(
            observation,
            situation_context,
            route,
        )
        cognitive_started_at = perf_counter()
        output = await self.app.process_observation(
            observation,
            situation_context=situation_context,
        )
        self.telemetry.record_stage(
            RuntimeLatencyStage.COGNITIVE_PROCESSING,
            cognitive_started_at,
            route=route,
            output_present=output.is_sendable,
        )
        self.telemetry.record(
            "runtime.cognitive.success",
            route=route,
            output_present=output.is_sendable,
        )
        await self._record_conversation_response(observation, output)
        await self._run_runtime_learning_event(
            kind=_runtime_learning_event_kind(output),
            observation=observation,
            output=output,
            route=route,
        )
        return self._complete_observation(output, route=route, started_at=started_at)

    async def _load_conversation_context(
        self,
        observation: Observation,
        situation_context: SituationContextSnapshot | None,
        route: str,
    ) -> SituationContextSnapshot | None:
        stage_started_at = perf_counter()
        if self.conversation_runtime is not None:
            situation_context = await self.conversation_runtime.load_context(
                observation,
                situation_context,
            )
        self.telemetry.record_stage(
            RuntimeLatencyStage.CONVERSATION_CONTEXT_LOAD,
            stage_started_at,
            route=route,
        )
        return situation_context

    async def _record_conversation_response(
        self,
        observation: Observation,
        output: PresentedOutput,
    ) -> None:
        stage_started_at = perf_counter()
        if self.conversation_runtime is not None:
            await self.conversation_runtime.record_response(observation, output)
        self.telemetry.record_stage(
            RuntimeLatencyStage.CONVERSATION_RECORD,
            stage_started_at,
            output_present=output.is_sendable,
        )

    async def _handle_activity_event(
        self,
        observation: ActivityEventObservation,
        situation_context: SituationContextSnapshot | None,
        ingress: ObservationIngressContext,
        started_at: float,
    ) -> PresentedOutput:
        route = "activity_event"
        if self.activity_event_reaction_handler is not None:
            self.telemetry.record("runtime.activity_reaction.start", route=route)
            output = await self.activity_event_reaction_handler.handle(
                observation,
                situation_context,
                ingress,
            )
            self.telemetry.record(
                "runtime.activity_reaction.success",
                route=route,
                output_present=output.is_sendable,
            )
        else:
            output = PresentedOutput(text=None)
        await self._run_runtime_learning_event(
            kind=_runtime_learning_event_kind(output),
            observation=observation,
            output=output,
            route=route,
        )
        return self._complete_observation(
            output,
            route=route,
            started_at=started_at,
            record_no_send=not output.is_sendable,
        )

    async def _handle_user_feedback(
        self,
        observation: Observation,
        started_at: float,
    ) -> PresentedOutput:
        route = "user_feedback"
        await self._run_runtime_learning_event(
            kind=RuntimeLearningEventKind.USER_FEEDBACK,
            observation=observation,
            output=None,
            route=route,
        )
        return self._complete_observation(
            PresentedOutput(text=None),
            route=route,
            started_at=started_at,
            record_no_send=True,
        )

    async def _run_runtime_learning_event(
        self,
        *,
        kind: RuntimeLearningEventKind,
        observation: Observation,
        output: PresentedOutput | None,
        route: str,
    ) -> None:
        stage_started_at = perf_counter()
        try:
            if self.runtime_learning_hook_runner is not None:
                event = RuntimeLearningEvent(
                    kind=kind,
                    observation=observation,
                    output=output,
                    occurred_at=self.now(),
                    route=route,
                    source_observation_id=observation.observation_id,
                )
                with bind_model_call_site(ModelCallSite.RUNTIME_LEARNING_HOOK):
                    await self.runtime_learning_hook_runner.run(event)
        finally:
            self.telemetry.record_stage(
                RuntimeLatencyStage.RUNTIME_LEARNING_HOOK,
                stage_started_at,
                route=route,
                output_present=output.is_sendable if output is not None else False,
            )

    def _complete_observation(
        self,
        output: PresentedOutput,
        *,
        route: str,
        started_at: float,
        record_no_send: bool = False,
    ) -> PresentedOutput:
        if record_no_send:
            self.telemetry.record(
                "runtime.observation.no_send",
                route=route,
                output_present=False,
            )
        self.telemetry.record(
            "runtime.observation.success",
            route=route,
            latency_ms=latency_ms(started_at),
            output_present=output.is_sendable,
        )
        return output


def _route_name(
    route: ActivityEventRoute | PresenceSignalRoute | UserFeedbackRoute | object,
) -> str:
    """Runtime route から安定した route 名を返す。

    Returns:
        安定した route 名。
    """
    if isinstance(route, ActivityEventRoute):
        return "activity_event"
    if isinstance(route, PresenceSignalRoute):
        return "presence_signal"
    if isinstance(route, UserFeedbackRoute):
        return "user_feedback"
    return "cognitive"


def _runtime_learning_event_kind(output: PresentedOutput) -> RuntimeLearningEventKind:
    """出力可能性から runtime 学習イベント種別を返す。

    Returns:
        Sendable output なら inline response、それ以外は no-action。
    """
    if output.is_sendable:
        return RuntimeLearningEventKind.INLINE_RESPONSE_GENERATED
    return RuntimeLearningEventKind.NO_ACTION
