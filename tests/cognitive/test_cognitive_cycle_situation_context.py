"""CognitiveCycle situation context propagation tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, override

import pytest

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import ActionSelectionResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.cycle.service import CognitiveCycle
from iris.contracts.actions import ActionPlan
from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.contracts.workspace_context import SituationContextSnapshot
from iris.core.ids import (
    AccountId,
    ActorId,
    DeviceId,
    ExternalRef,
    ObservationId,
    SessionId,
    SpaceId,
)

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame


class _RecordingStep(PipelineStep[ActionSelectionResult]):
    """A step that records the situation_context it receives."""

    name = "recording"

    def __init__(self) -> None:
        self.frames: list[WorkspaceFrame] = []

    @override
    async def run(self, frame: WorkspaceFrame) -> ActionSelectionResult:
        self.frames.append(frame)
        return ActionSelectionResult(
            step_name=self.name,
            status=StepStatus.OK,
            action_plans=(),
        )


def _observation() -> ActorMessageObservation:
    """Build a simple observation for cycle tests.

    Returns:
        ActorMessageObservation: A test observation.
    """
    return ActorMessageObservation(
        observation_id=ObservationId("obs-cycle"),
        session_id=SessionId("session-cycle"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-cycle"),
                actor_kind=ActorKind.HUMAN,
                display_name="Mina",
                provider="test",
                provider_subject=ExternalRef("mina"),
            ),
            account_id=AccountId("account-cycle"),
            device_id=DeviceId("device-cycle"),
            space_id=SpaceId("space-cycle"),
        ),
        occurred_at=datetime(2026, 6, 13, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
    )


def _fallback_plan() -> ActionPlan:
    """Return a canonical no_action fallback plan.

    Returns:
        ActionPlan: no_action fallback plan.
    """
    return ActionPlan(
        turn_intent="no_action",
        candidate_text=None,
        should_respond=False,
        priority=-1,
    )


@pytest.mark.asyncio
async def test_run_without_situation_context_passes_empty_snapshot() -> None:
    """Situation_context なしでは空の snapshot がパイプラインに渡される。"""
    step = _RecordingStep()
    cycle = CognitiveCycle(
        steps=[step],
        frame_builder=FrameBuilder(),
        fallback_plan=_fallback_plan(),
    )

    await cycle.run(_observation())

    assert len(step.frames) == 1
    assert step.frames[0].situation_context == SituationContextSnapshot()


@pytest.mark.asyncio
async def test_run_propagates_situation_context() -> None:
    """Run に渡した situation_context がパイプラインで利用できる。"""
    situation = SituationContextSnapshot(
        availability=AvailabilitySnapshot(
            actor_id=ActorId("actor-cycle"),
            status=AvailabilityStatus.AVAILABLE,
            reason="test",
            observed_at=datetime(2026, 6, 13, tzinfo=UTC),
            computed_at=datetime(2026, 6, 13, tzinfo=UTC),
        ),
    )
    step = _RecordingStep()
    cycle = CognitiveCycle(
        steps=[step],
        frame_builder=FrameBuilder(),
        fallback_plan=_fallback_plan(),
    )

    await cycle.run(_observation(), situation_context=situation)

    assert len(step.frames) == 1
    assert step.frames[0].situation_context is situation
