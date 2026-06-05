"""Runtime service boundary tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.cognitive.cycle.models import ActionSelectionResult, StepStatus
from iris.contracts.actions import ActionPlan, PresentedOutput
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import CorrelationId, ObservationId, SessionId
from iris.runtime.app import IrisApp
from iris.runtime.config import default_runtime_config
from iris.runtime.service import IrisRuntimeService, ObservationEnvelope, RuntimeResponse
from iris.runtime.wiring.app import build_app_from_config, wire_default_app
from tests.helpers.immutability import assert_frozen_field

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame


@pytest.mark.anyio
async def test_runtime_service_handles_actor_message_envelope() -> None:
    """ActorMessageObservationをObservationEnvelope経由で処理できることを確認する。"""
    app = wire_default_app(FakeLLMClient(responses=("service response",)))
    service = IrisRuntimeService(app)
    envelope = ObservationEnvelope(
        observation=_actor_message("hello"),
        correlation_id=CorrelationId("corr-1"),
    )

    response = await service.handle_observation(envelope)

    assert isinstance(response, RuntimeResponse)
    assert isinstance(response.output, PresentedOutput)
    assert response.output.text == "service response"
    assert response.correlation_id == CorrelationId("corr-1")


@pytest.mark.anyio
async def test_runtime_service_preserves_no_action_output() -> None:
    """no_action結果もRuntimeResponseとして返ることを確認する。"""
    app = IrisApp(steps=(_NoActionStep(),))
    service = IrisRuntimeService(app)

    response = await service.handle_observation(
        ObservationEnvelope(
            observation=_actor_message("   "),
            correlation_id=CorrelationId("corr-no-action"),
        )
    )

    assert response.output == PresentedOutput(text=None)
    assert response.correlation_id == CorrelationId("corr-no-action")


@pytest.mark.anyio
async def test_runtime_service_full_cycle_app_from_config() -> None:
    """build_app_from_configで作ったfull-cycle appがRuntimeService経由で動作することを確認する。"""
    service = IrisRuntimeService(build_app_from_config(default_runtime_config()))

    response = await service.handle_observation(
        ObservationEnvelope(
            observation=_actor_message("hello service"),
            correlation_id=CorrelationId("corr-full-cycle"),
        )
    )

    assert isinstance(response.output, PresentedOutput)
    assert response.output.text == "fake response: hello service"
    assert response.correlation_id == CorrelationId("corr-full-cycle")


def test_runtime_service_contracts_are_frozen() -> None:
    """ObservationEnvelopeとRuntimeResponseがfrozen dataclassであることを確認する。"""
    envelope = ObservationEnvelope(observation=_actor_message("immutable"))
    response = RuntimeResponse(output=PresentedOutput(text="immutable"))

    assert_frozen_field(envelope, "correlation_id", CorrelationId("changed"))
    assert_frozen_field(response, "correlation_id", CorrelationId("changed"))


def _actor_message(text: str) -> ActorMessageObservation:
    """ActorMessageObservation test fixtureを作る。

    Returns:
        ActorMessageObservation: RuntimeServiceへ渡す観測。
    """
    return ActorMessageObservation(
        observation_id=ObservationId("runtime-service-observation"),
        session_id=SessionId("runtime-service-session"),
        context=ObservationContext(),
        occurred_at=datetime(2026, 6, 5, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )


class _NoActionStep:
    """Test pipeline step that always selects canonical no_action."""

    name = "no_action"

    async def run(self, frame: WorkspaceFrame) -> ActionSelectionResult:
        """Return canonical no_action selection.

        Returns:
            ActionSelectionResult: no_action candidate plan.
        """
        _ = frame.observation
        return ActionSelectionResult(
            step_name=self.name,
            status=StepStatus.OK,
            action_plans=(
                ActionPlan(
                    turn_intent="no_action",
                    candidate_text=None,
                    should_respond=False,
                    priority=-1,
                ),
            ),
        )
