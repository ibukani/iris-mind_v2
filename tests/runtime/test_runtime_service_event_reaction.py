"""IrisRuntimeService への event reaction 統合 tests。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from iris.cognitive.cycle.models import ActionSelectionResult, PipelineStepResult, StepStatus
from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.activity import ActivityKind
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActivityEventObservation,
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
    PresenceSignalObservation,
)
from iris.contracts.presence import PresenceStatus
from iris.core.ids import ActorId, ObservationId, SessionId, SpaceId
from iris.runtime.app import IrisApp
from iris.runtime.config import default_runtime_config
from iris.runtime.event_reaction.handler import ActivityEventReactionHandler
from iris.runtime.observations.ingress import (
    ObservationCapability,
    ObservationIngressContext,
)
from iris.runtime.observations.trust import ObservationTrustPolicy
from iris.runtime.presence.integrator import PresenceIntegrator
from iris.runtime.server import build_runtime_service
from iris.runtime.service import (
    IntegratingObservationPipeline,
    IrisRuntimeService,
    ObservationEnvelope,
)
from iris.runtime.wiring.availability import wire_availability_resolver
from iris.runtime.wiring.context import wire_workspace_context_assembler
from iris.runtime.wiring.event_reaction import wire_event_reaction_runner
from iris.runtime.wiring.state import wire_runtime_state
from iris.safety.action_gate import GateDecision, SafetyDecision

if TYPE_CHECKING:
    from iris.contracts.actions import PresentedOutput


_OCCURRED_AT = datetime(2026, 6, 13, tzinfo=UTC)
_RECEIVED_AT = _OCCURRED_AT + timedelta(seconds=1)
_ACTOR_ID = ActorId("actor-1")
_SPACE_ID = SpaceId("space-1")


@dataclass
class _CaptureFrameStep:
    """WorkspaceFrameをキャプチャし、空のaction selection結果を返すtest step。"""

    name: str = "capture"
    frames: list[WorkspaceFrame] = field(default_factory=list[WorkspaceFrame])

    async def run(self, frame: WorkspaceFrame) -> PipelineStepResult:
        self.frames.append(frame)
        return ActionSelectionResult(
            step_name=self.name,
            status=StepStatus.OK,
            action_plans=(),
        )


def _identity() -> Identity:
    return Identity(
        actor_id=_ACTOR_ID,
        actor_kind=ActorKind.HUMAN,
        display_name="Actor",
    )


def _ingress(
    *capabilities: ObservationCapability,
) -> ObservationIngressContext:
    return ObservationIngressContext(
        adapter_id="trusted-adapter",
        provider="test",
        authenticated=True,
        capabilities=frozenset(capabilities),
    )


def _unauthenticated_ingress(
    *capabilities: ObservationCapability,
) -> ObservationIngressContext:
    return ObservationIngressContext(
        adapter_id="external_client",
        provider=None,
        authenticated=False,
        capabilities=frozenset(capabilities),
    )


@dataclass(frozen=True)
class _BlockAllOutputGate:
    async def check_output(self, output: PresentedOutput) -> SafetyDecision:
        _ = self, output
        return SafetyDecision(
            decision=GateDecision.BLOCK,
            reason="blocked in test",
        )


def _presence_observation() -> PresenceSignalObservation:
    return PresenceSignalObservation(
        observation_id=ObservationId("obs-presence"),
        session_id=SessionId("session-1"),
        context=ObservationContext(
            actor=_identity(),
            source="test",
        ),
        occurred_at=_OCCURRED_AT,
        kind=ObservationKind.PRESENCE_SIGNAL,
        status=PresenceStatus.ONLINE,
    )


def _activity_observation(kind: ActivityKind) -> ActivityEventObservation:
    return ActivityEventObservation(
        observation_id=ObservationId(f"obs-{kind.value}"),
        session_id=SessionId("session-1"),
        context=ObservationContext(
            actor=_identity(),
            space_id=_SPACE_ID,
            source="test",
        ),
        occurred_at=_OCCURRED_AT,
        kind=ObservationKind.ACTIVITY_EVENT,
        activity_kind=kind,
    )


def _message_observation() -> ActorMessageObservation:
    return ActorMessageObservation(
        observation_id=ObservationId("obs-msg"),
        session_id=SessionId("session-1"),
        context=ObservationContext(
            actor=_identity(),
            source="test",
        ),
        occurred_at=_OCCURRED_AT,
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
    )


@pytest.fixture
def service_setup() -> tuple[IrisRuntimeService, _CaptureFrameStep]:
    """Event reaction runnerまで配線されたIrisRuntimeServiceとcapture stepを提供する。

    Returns:
        tuple[IrisRuntimeService, _CaptureFrameStep]: サービスとcapture step。
    """
    config = default_runtime_config()
    stores = wire_runtime_state(config)
    capture = _CaptureFrameStep()
    app = IrisApp(steps=[capture])
    service: IrisRuntimeService = build_runtime_service(
        app,
        stores,
        now=lambda: _RECEIVED_AT,
    )
    return service, capture


@pytest.mark.anyio
async def test_presence_signal_still_no_send(
    service_setup: tuple[IrisRuntimeService, _CaptureFrameStep],
) -> None:
    """PresenceSignalObservationはstate-onlyで送信しない。"""
    service, _capture = service_setup
    response = await service.handle_observation(
        ObservationEnvelope(
            observation=_presence_observation(),
            ingress=_ingress(ObservationCapability.INTEGRATE_PRESENCE),
        ),
    )

    assert not response.output.is_sendable


@pytest.mark.anyio
async def test_voice_joined_reacts_after_presence_and_activity_integration(
    service_setup: tuple[IrisRuntimeService, _CaptureFrameStep],
) -> None:
    """Presence + activity統合後、VOICE_JOINEDに対してevent reactionを返す。"""
    service, _capture = service_setup

    await service.handle_observation(
        ObservationEnvelope(
            observation=_presence_observation(),
            ingress=_ingress(ObservationCapability.INTEGRATE_PRESENCE),
        ),
    )

    response = await service.handle_observation(
        ObservationEnvelope(
            observation=_activity_observation(ActivityKind.VOICE_JOINED),
            ingress=_ingress(
                ObservationCapability.INTEGRATE_ACTIVITY,
                ObservationCapability.UPDATE_SPACE_OCCUPANCY,
                ObservationCapability.REACT_TO_ACTIVITY,
            ),
        ),
    )

    assert response.output.is_sendable
    assert response.output.text == "Welcome back."
    assert response.output.style_hint == "event_reaction"
    assert response.output.priority == 10


@pytest.mark.anyio
async def test_app_opened_reacts_when_available(
    service_setup: tuple[IrisRuntimeService, _CaptureFrameStep],
) -> None:
    """APP_OPENEDもAVAILABLEな状況でevent reactionを返す。"""
    service, _capture = service_setup

    await service.handle_observation(
        ObservationEnvelope(
            observation=_presence_observation(),
            ingress=_ingress(ObservationCapability.INTEGRATE_PRESENCE),
        ),
    )

    response = await service.handle_observation(
        ObservationEnvelope(
            observation=_activity_observation(ActivityKind.APP_OPENED),
            ingress=_ingress(
                ObservationCapability.INTEGRATE_ACTIVITY,
                ObservationCapability.REACT_TO_ACTIVITY,
            ),
        ),
    )

    assert response.output.is_sendable
    assert response.output.text == "Welcome back. I am here if you want to talk."
    assert response.output.priority == 5


@pytest.mark.anyio
async def test_voice_left_no_reaction(
    service_setup: tuple[IrisRuntimeService, _CaptureFrameStep],
) -> None:
    """VOICE_LEFTは反応しない。"""
    service, _capture = service_setup

    await service.handle_observation(
        ObservationEnvelope(
            observation=_presence_observation(),
            ingress=_ingress(ObservationCapability.INTEGRATE_PRESENCE),
        ),
    )

    response = await service.handle_observation(
        ObservationEnvelope(
            observation=_activity_observation(ActivityKind.VOICE_LEFT),
            ingress=_ingress(ObservationCapability.INTEGRATE_ACTIVITY),
        ),
    )

    assert not response.output.is_sendable


@pytest.mark.anyio
async def test_actor_message_passes_to_app_with_situation_context(
    service_setup: tuple[IrisRuntimeService, _CaptureFrameStep],
) -> None:
    """ActorMessageObservationはevent reactionを経由せずAppに渡される。"""
    service, capture = service_setup
    response = await service.handle_observation(
        ObservationEnvelope(
            observation=_message_observation(),
            ingress=_ingress(),
        ),
    )

    assert not response.output.is_sendable
    assert len(capture.frames) == 1
    frame = capture.frames[0]
    assert frame.observation.kind is ObservationKind.ACTOR_MESSAGE
    assert frame.situation_context.availability is not None


@pytest.mark.anyio
async def test_unauthenticated_activity_event_does_not_react(
    service_setup: tuple[IrisRuntimeService, _CaptureFrameStep],
) -> None:
    """未認証のingressではevent reactionを実行しない。"""
    service, _capture = service_setup

    await service.handle_observation(
        ObservationEnvelope(
            observation=_presence_observation(),
            ingress=_ingress(ObservationCapability.INTEGRATE_PRESENCE),
        ),
    )

    response = await service.handle_observation(
        ObservationEnvelope(
            observation=_activity_observation(ActivityKind.VOICE_JOINED),
            ingress=_unauthenticated_ingress(ObservationCapability.INTEGRATE_ACTIVITY),
        ),
    )

    assert not response.output.is_sendable


@pytest.mark.anyio
async def test_activity_event_without_reaction_or_integrate_capability_does_not_react(
    service_setup: tuple[IrisRuntimeService, _CaptureFrameStep],
) -> None:
    """REACT_TO_ACTIVITY/INTEGRATE_ACTIVITYがないingressではevent reactionを実行しない。"""
    service, _capture = service_setup

    await service.handle_observation(
        ObservationEnvelope(
            observation=_presence_observation(),
            ingress=_ingress(ObservationCapability.INTEGRATE_PRESENCE),
        ),
    )

    response = await service.handle_observation(
        ObservationEnvelope(
            observation=_activity_observation(ActivityKind.VOICE_JOINED),
            ingress=_ingress(ObservationCapability.INTEGRATE_PRESENCE),
        ),
    )

    assert not response.output.is_sendable


@pytest.mark.anyio
async def test_trusted_activity_event_reacts(
    service_setup: tuple[IrisRuntimeService, _CaptureFrameStep],
) -> None:
    """信頼されたingressではevent reactionが実行される。"""
    service, _capture = service_setup

    await service.handle_observation(
        ObservationEnvelope(
            observation=_presence_observation(),
            ingress=_ingress(ObservationCapability.INTEGRATE_PRESENCE),
        ),
    )

    response = await service.handle_observation(
        ObservationEnvelope(
            observation=_activity_observation(ActivityKind.VOICE_JOINED),
            ingress=_ingress(
                ObservationCapability.INTEGRATE_ACTIVITY,
                ObservationCapability.REACT_TO_ACTIVITY,
            ),
        ),
    )

    assert response.output.is_sendable
    assert response.output.text == "Welcome back."
    assert response.output.style_hint == "event_reaction"


@pytest.mark.anyio
async def test_blocking_output_gate_prevents_sendable_reaction() -> None:
    """Output safety gateがBLOCKするとevent reaction出力は送信されない。"""
    config = default_runtime_config()
    stores = wire_runtime_state(config)
    capture = _CaptureFrameStep()
    app = IrisApp(steps=[capture])

    trust_policy = ObservationTrustPolicy()

    def _now() -> datetime:
        return _RECEIVED_AT

    presence_integrator = PresenceIntegrator(
        store=stores.presence_store,
        trust_policy=trust_policy,
        now=_now,
    )
    availability_resolver = wire_availability_resolver()
    workspace_context_assembler = wire_workspace_context_assembler(
        activity_projection_store=stores.activity_projection_store,
        presence_store=stores.presence_store,
        occupancy_store=stores.space_occupancy_store,
        availability_resolver=availability_resolver,
        now=_now,
    )
    event_reaction_runner = wire_event_reaction_runner()

    handler = ActivityEventReactionHandler(
        trust_policy=trust_policy,
        runner=event_reaction_runner,
        output_gate=_BlockAllOutputGate(),
    )

    service = IrisRuntimeService(
        app,
        observation_pipeline=IntegratingObservationPipeline((presence_integrator,)),
        workspace_context_assembler=workspace_context_assembler,
        activity_event_reaction_handler=handler,
    )

    await service.handle_observation(
        ObservationEnvelope(
            observation=_presence_observation(),
            ingress=_ingress(ObservationCapability.INTEGRATE_PRESENCE),
        ),
    )

    response = await service.handle_observation(
        ObservationEnvelope(
            observation=_activity_observation(ActivityKind.VOICE_JOINED),
            ingress=_ingress(
                ObservationCapability.INTEGRATE_ACTIVITY,
                ObservationCapability.REACT_TO_ACTIVITY,
            ),
        ),
    )

    assert not response.output.is_sendable
