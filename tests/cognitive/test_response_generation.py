from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from iris.cognitive.action.response import (
    GeneratedResponse,
    ResponseGenerationStep,
    ResponsePrompt,
    build_response_prompt,
)
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import StepStatus
from iris.cognitive.perception.basic import SimplePerceptionStep
from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.observations import ObservationKind, UserMessageObservation
from iris.core.ids import ObservationId, SessionId


class StubResponseGenerator:
    def __init__(self, response_text: str) -> None:
        self.prompts: list[ResponsePrompt] = []
        self._response_text = response_text

    async def generate_response(self, prompt: ResponsePrompt) -> GeneratedResponse:
        self.prompts.append(prompt)
        return GeneratedResponse(text=self._response_text, model="stub")


def user_message(text: str = "hello") -> UserMessageObservation:
    return UserMessageObservation(
        observation_id=ObservationId("obs-response"),
        session_id=SessionId("session-response"),
        actor=None,
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.USER_MESSAGE,
        text=text,
    )


@pytest.mark.anyio
async def test_response_generation_step_converts_frame_text_into_action_plan() -> None:
    frame_builder = FrameBuilder()
    frame = WorkspaceFrame(observation=user_message("what is new?"))
    perceived = await SimplePerceptionStep().run(frame)
    frame = frame_builder.apply(frame, perceived)
    generator = StubResponseGenerator("generated reply")

    result = await ResponseGenerationStep(generator).run(frame)
    frame_after_response = frame_builder.apply(frame, result)

    assert result.status == StepStatus.OK
    assert generator.prompts == [
        ResponsePrompt(
            system_instruction="Generate a concise text response for Iris.",
            user_text="what is new?",
        ),
    ]
    assert frame_after_response.candidate_action_plans[0].candidate_text == "generated reply"
    assert frame_after_response.candidate_action_plans[0].should_respond is True
    assert frame_after_response.candidate_action_plans[0].turn_intent == "respond"


@pytest.mark.anyio
async def test_response_generation_skips_when_frame_has_no_interpreted_text() -> None:
    frame = WorkspaceFrame(observation=user_message())
    generator = StubResponseGenerator("unused")

    result = await ResponseGenerationStep(generator).run(frame)

    assert result.status == StepStatus.SKIPPED
    assert result.action_plans == ()
    assert generator.prompts == []


def test_response_generation_does_not_mutate_workspace_frame_directly() -> None:
    frame = WorkspaceFrame(observation=user_message())

    with pytest.raises(FrozenInstanceError):
        frame.candidate_action_plans = ()  # type: ignore[misc]

    assert build_response_prompt(frame) is None
