"""RuntimeService runtime learning event tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, override

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.cognitive.cycle.models import ActionSelectionResult, StepStatus
from iris.contracts.actions import ActionPlan, PresentedOutput
from iris.contracts.activity import ActivityKind
from iris.contracts.learning import RuntimeLearningEvent, RuntimeLearningEventKind
from iris.contracts.observations import (
    ActivityEventObservation,
    ActorMessageObservation,
    Observation,
    ObservationContext,
    ObservationKind,
    PresenceSignalObservation,
    UserFeedbackKind,
    UserFeedbackObservation,
)
from iris.contracts.presence import PresenceStatus
from iris.core.ids import CorrelationId, ObservationId, SessionId
from iris.runtime.app import IrisApp
from iris.runtime.learning.hooks import RuntimeLearningHookRunner
from iris.runtime.service import IrisRuntimeService, ObservationEnvelope, RuntimeServiceExtensions
from iris.runtime.wiring.app import wire_default_app
from tests.helpers.output_pipeline import make_output_pipeline

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame
    from iris.contracts.workspace_context import SituationContextSnapshot
    from iris.runtime.ingress.observation_ingress import ObservationIngressContext

pytestmark = pytest.mark.anyio

_NOW = datetime(2026, 7, 1, 1, tzinfo=UTC)


@pytest.mark.anyio
async def test_sendable_cognitive_output_dispatches_inline_runtime_learning_event() -> None:
    """Sendable cognitive outputをinline response learning eventとしてdispatchする。"""
    hook = _RecordingRuntimeLearningHook()
    service = IrisRuntimeService(
        wire_default_app(FakeLLMClient(responses=("service response",))),
        extensions=RuntimeServiceExtensions(
            runtime_learning_hook_runner=RuntimeLearningHookRunner((hook,))
        ),
        now=lambda: _NOW,
    )
    observation = _actor_message("hello")

    response = await service.handle_observation(
        ObservationEnvelope.external_client(observation=observation)
    )

    assert response.output.text == "service response"
    assert len(hook.events) == 1
    event = hook.events[0]
    assert event.kind is RuntimeLearningEventKind.INLINE_RESPONSE_GENERATED
    assert event.observation is observation
    assert event.output == response.output
    assert event.occurred_at == _NOW
    assert event.route == "cognitive"
    assert event.source_observation_id == observation.observation_id


async def test_no_action_cognitive_output_dispatches_no_action_runtime_learning_event() -> None:
    """no-action cognitive outputをno_action learning eventとしてdispatchする。"""
    hook = _RecordingRuntimeLearningHook()
    app = _no_action_app()
    service = IrisRuntimeService(
        app,
        extensions=RuntimeServiceExtensions(
            runtime_learning_hook_runner=RuntimeLearningHookRunner((hook,))
        ),
        now=lambda: _NOW,
    )
    observation = _actor_message(" ")

    response = await service.handle_observation(
        ObservationEnvelope.external_client(observation=observation)
    )

    assert response.output == PresentedOutput(text=None)
    assert len(hook.events) == 1
    event = hook.events[0]
    assert event.kind is RuntimeLearningEventKind.NO_ACTION
    assert event.output == response.output
    assert event.route == "cognitive"


async def test_runtime_learning_hook_failure_does_not_fail_runtime_response() -> None:
    """Runtime hook failureはuser-facing RuntimeResponseを壊さない。"""
    hook = _FailingRuntimeLearningHook()
    service = IrisRuntimeService(
        wire_default_app(FakeLLMClient(responses=("still returned",))),
        extensions=RuntimeServiceExtensions(
            runtime_learning_hook_runner=RuntimeLearningHookRunner((hook,))
        ),
    )

    response = await service.handle_observation(
        ObservationEnvelope.external_client(observation=_actor_message("hello"))
    )

    assert response.output.text == "still returned"
    assert hook.calls == 1


async def test_user_feedback_dispatches_feedback_event_without_cognitive_processing() -> None:
    """UserFeedbackObservationはcognitive cycleに流さずUSER_FEEDBACK eventをdispatchする。"""
    hook = _RecordingRuntimeLearningHook()
    conversation_runtime = _RecordingConversationRuntime()
    service = IrisRuntimeService(
        _FailingApp(),
        extensions=RuntimeServiceExtensions(
            conversation_runtime=conversation_runtime,
            runtime_learning_hook_runner=RuntimeLearningHookRunner((hook,)),
        ),
        now=lambda: _NOW,
    )
    observation = _user_feedback("もっと短く答えて")

    response = await service.handle_observation(
        ObservationEnvelope.external_client(
            observation=observation,
            correlation_id=CorrelationId("corr-feedback"),
        )
    )

    assert response.output == PresentedOutput(text=None)
    assert response.correlation_id == CorrelationId("corr-feedback")
    assert len(hook.events) == 1
    event = hook.events[0]
    assert event.kind is RuntimeLearningEventKind.USER_FEEDBACK
    assert event.observation is observation
    assert event.output is None
    assert event.route == "user_feedback"
    assert event.source_observation_id == observation.observation_id
    assert conversation_runtime.loaded == []
    assert conversation_runtime.recorded == []


async def test_activity_event_sendable_output_dispatches_inline_runtime_learning_event() -> None:
    """Activity reactionのsendable outputをinline learning eventとしてdispatchする。"""
    hook = _RecordingRuntimeLearningHook()
    service = IrisRuntimeService(
        _FailingApp(),
        activity_event_reaction_handler=_StaticActivityHandler(
            PresentedOutput(text="Welcome back")
        ),
        extensions=RuntimeServiceExtensions(
            runtime_learning_hook_runner=RuntimeLearningHookRunner((hook,))
        ),
    )
    observation = _activity_event()

    response = await service.handle_observation(
        ObservationEnvelope.external_client(observation=observation)
    )

    assert response.output.text == "Welcome back"
    assert len(hook.events) == 1
    assert hook.events[0].kind is RuntimeLearningEventKind.INLINE_RESPONSE_GENERATED
    assert hook.events[0].route == "activity_event"
    assert hook.events[0].observation is observation


async def test_activity_event_no_send_output_dispatches_no_action_runtime_learning_event() -> None:
    """Activity reactionのno-send outputをno_action learning eventとしてdispatchする。"""
    hook = _RecordingRuntimeLearningHook()
    service = IrisRuntimeService(
        _FailingApp(),
        activity_event_reaction_handler=_StaticActivityHandler(PresentedOutput(text=None)),
        extensions=RuntimeServiceExtensions(
            runtime_learning_hook_runner=RuntimeLearningHookRunner((hook,))
        ),
    )

    response = await service.handle_observation(
        ObservationEnvelope.external_client(observation=_activity_event())
    )

    assert response.output == PresentedOutput(text=None)
    assert len(hook.events) == 1
    assert hook.events[0].kind is RuntimeLearningEventKind.NO_ACTION
    assert hook.events[0].route == "activity_event"


async def test_presence_signal_does_not_dispatch_runtime_learning_event() -> None:
    """Presence signal統合はruntime learning eventを発火しない。"""
    hook = _RecordingRuntimeLearningHook()
    service = IrisRuntimeService(
        _FailingApp(),
        extensions=RuntimeServiceExtensions(
            runtime_learning_hook_runner=RuntimeLearningHookRunner((hook,))
        ),
    )

    response = await service.handle_observation(
        ObservationEnvelope.external_client(observation=_presence_signal())
    )

    assert response.output == PresentedOutput(text=None)
    assert hook.events == []


def _actor_message(text: str) -> ActorMessageObservation:
    return ActorMessageObservation(
        observation_id=ObservationId(f"obs-{abs(hash(text))}"),
        session_id=SessionId("session-1"),
        context=ObservationContext(),
        occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )


def _activity_event() -> ActivityEventObservation:
    return ActivityEventObservation(
        observation_id=ObservationId("obs-activity-learning"),
        session_id=SessionId("session-1"),
        context=ObservationContext(),
        occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
        kind=ObservationKind.ACTIVITY_EVENT,
        activity_kind=ActivityKind.SYSTEM_INTERACTION,
    )


def _presence_signal() -> PresenceSignalObservation:
    return PresenceSignalObservation(
        observation_id=ObservationId("obs-presence-learning"),
        session_id=SessionId("session-1"),
        context=ObservationContext(),
        occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
        kind=ObservationKind.PRESENCE_SIGNAL,
        status=PresenceStatus.ONLINE,
    )


def _user_feedback(text: str) -> UserFeedbackObservation:
    return UserFeedbackObservation(
        observation_id=ObservationId("obs-feedback-learning"),
        session_id=SessionId("session-1"),
        context=ObservationContext(),
        occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
        kind=ObservationKind.USER_FEEDBACK,
        feedback_kind=UserFeedbackKind.STYLE_PREFERENCE,
        text=text,
    )


def _no_action_app() -> IrisApp:
    return IrisApp(output_pipeline=make_output_pipeline(), steps=(_NoActionStep(),))


class _NoActionStep:
    """Test pipeline step that selects canonical no_action."""

    name = "no_action"

    async def run(self, frame: WorkspaceFrame) -> ActionSelectionResult:
        """Return canonical no_action selection."""
        _ = frame.observation
        return ActionSelectionResult(
            step_name=self.name,
            status=StepStatus.OK,
            action_plans=(ActionPlan.no_action(),),
        )


@dataclass
class _RecordingRuntimeLearningHook:
    events: list[RuntimeLearningEvent] = field(default_factory=list[RuntimeLearningEvent])

    async def after_runtime_event(self, event: RuntimeLearningEvent) -> None:
        self.events.append(event)


@dataclass
class _FailingRuntimeLearningHook:
    calls: int = 0

    async def after_runtime_event(self, event: RuntimeLearningEvent) -> None:
        _ = event
        self.calls += 1
        message = "runtime hook failed"
        raise RuntimeError(message)


class _FailingApp(IrisApp):
    def __init__(self) -> None:
        super().__init__(output_pipeline=make_output_pipeline(), steps=(_NoActionStep(),))

    @override
    async def process_observation(
        self,
        observation: Observation,
        *,
        situation_context: SituationContextSnapshot | None = None,
    ) -> PresentedOutput:
        _ = observation, situation_context
        message = "app should not be called"
        raise AssertionError(message)


@dataclass
class _RecordingConversationRuntime:
    loaded: list[Observation] = field(default_factory=list[Observation])
    recorded: list[tuple[Observation, PresentedOutput]] = field(
        default_factory=list[tuple[Observation, PresentedOutput]]
    )

    async def load_context(
        self,
        observation: Observation,
        base: SituationContextSnapshot | None,
    ) -> SituationContextSnapshot:
        self.loaded.append(observation)
        if base is None:
            message = "load_context should not be called without a situation context"
            raise AssertionError(message)
        return base

    async def record_response(self, observation: Observation, output: PresentedOutput) -> None:
        self.recorded.append((observation, output))


@dataclass(frozen=True)
class _StaticActivityHandler:
    output: PresentedOutput

    async def handle(
        self,
        observation: ActivityEventObservation,
        situation_context: SituationContextSnapshot | None,
        ingress: ObservationIngressContext,
    ) -> PresentedOutput:
        _ = observation, situation_context, ingress
        return self.output
