"""応答生成パイプラインステップとプロンプト構築のテスト。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import StepStatus
from iris.cognitive.perception.basic import SimplePerceptionStep
from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.conversation import ConversationRecord, ConversationRole, ConversationWindow
from iris.contracts.observations import (
    ActorMessageObservation,
    IdleTickObservation,
    ObservationContext,
    ObservationKind,
)
from iris.contracts.workspace_context import SituationContextSnapshot
from iris.core.ids import ObservationId, SessionId
from iris.features.chat.definition import (
    GeneratedResponse,
    ResponseGenerationStep,
    ResponsePrompt,
    build_response_prompt,
)
from tests.helpers.immutability import assert_frozen_field


class StubResponseGenerator:
    """プロンプトを記録して固定応答を返すスタブ応答生成器。"""

    def __init__(self, response_text: str) -> None:
        """固定応答テキストで初期化する。"""
        self.prompts: list[ResponsePrompt] = []
        self._response_text = response_text

    async def generate_response(self, prompt: ResponsePrompt) -> GeneratedResponse:
        """プロンプトを記録して固定応答を返す。

        Returns:
            GeneratedResponse: 事前定義された固定応答。
        """
        self.prompts.append(prompt)
        return GeneratedResponse(text=self._response_text, model="stub")


def actor_message(text: str = "hello") -> ActorMessageObservation:
    """指定されたテキストを持つActorMessageObservationを返す。

    Returns:
        ActorMessageObservation: 構築済みの観測。
    """
    return ActorMessageObservation(
        observation_id=ObservationId("obs-response"),
        session_id=SessionId("session-response"),
        context=ObservationContext(),
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )


@pytest.mark.anyio
async def test_response_generation_step_converts_frame_text_into_action_plan() -> None:
    """ResponseGenerationStepが解釈テキストからActionPlanを生成することを確認する。"""
    frame_builder = FrameBuilder()
    frame = WorkspaceFrame(observation=actor_message("what is new?"))
    perceived = await SimplePerceptionStep().run(frame)
    frame = frame_builder.apply(frame, perceived)
    generator = StubResponseGenerator("generated reply")

    result = await ResponseGenerationStep(generator).run(frame)
    frame_after_response = frame_builder.apply(frame, result)

    assert result.status == StepStatus.OK
    assert generator.prompts == [
        ResponsePrompt(
            system_instruction=(
                "Generate a concise text response for Iris. "
                "Respond directly without showing your thinking or reasoning process."
            ),
            actor_text="what is new?",
        ),
    ]
    assert frame_after_response.candidate_action_plans[0].candidate_text == "generated reply"
    assert frame_after_response.candidate_action_plans[0].should_respond is True
    assert frame_after_response.candidate_action_plans[0].turn_intent == "respond"


@pytest.mark.anyio
async def test_response_generation_skips_when_frame_has_no_interpreted_text() -> None:
    """フレームに解釈テキストがない場合にResponseGenerationStepがスキップすることを確認する。"""
    frame = WorkspaceFrame(observation=actor_message())
    generator = StubResponseGenerator("unused")

    result = await ResponseGenerationStep(generator).run(frame)

    assert result.status == StepStatus.SKIPPED
    assert result.action_plans == ()
    assert generator.prompts == []


@pytest.mark.anyio
async def test_response_generation_skips_non_actor_observation_text() -> None:
    """内部観測の知覚ラベルをactor向け応答プロンプトへ変換しない。"""
    frame_builder = FrameBuilder()
    frame = WorkspaceFrame(
        observation=IdleTickObservation(
            observation_id=ObservationId("obs-idle-response"),
            session_id=SessionId("session-idle-response"),
            context=ObservationContext(),
            occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
            kind=ObservationKind.IDLE_TICK,
            idle_seconds=600.0,
        ),
    )
    perceived = await SimplePerceptionStep().run(frame)
    frame = frame_builder.apply(frame, perceived)
    generator = StubResponseGenerator("must not be generated")

    result = await ResponseGenerationStep(generator).run(frame)

    assert result.status == StepStatus.SKIPPED
    assert result.action_plans == ()
    assert generator.prompts == []


def test_response_generation_does_not_mutate_workspace_frame_directly() -> None:
    """WorkspaceFrame.candidate_action_plansがその場で変更できないことを確認する。"""
    frame = WorkspaceFrame(observation=actor_message())

    assert_frozen_field(frame, "candidate_action_plans", ())
    assert build_response_prompt(frame) is None


@pytest.mark.anyio
async def test_conversation_window_reaches_frame_and_response_prompt() -> None:
    """Runtime会話windowをframe経由でresponse promptへ渡す。"""
    previous = ConversationRecord(
        role=ConversationRole.USER,
        content="previous",
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        observation_id=ObservationId("obs-previous"),
        session_id=SessionId("session-previous"),
    )
    builder = FrameBuilder()
    frame = builder.build_initial(
        actor_message("current"),
        situation_context=SituationContextSnapshot(
            conversation_window=ConversationWindow(records=(previous,))
        ),
    )
    frame = builder.apply(frame, await SimplePerceptionStep().run(frame))
    prompt = build_response_prompt(frame)
    assert frame.conversation_history == (previous,)
    assert prompt is not None
    assert prompt.conversation_history == (previous,)
