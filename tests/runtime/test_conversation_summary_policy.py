"""Long conversation summary policy tests。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.ports import LLMRole
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import PerceptionResult, StepStatus
from iris.contracts.conversation import ConversationRecord, ConversationRole, ConversationWindow
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.contracts.workspace_context import SituationContextSnapshot
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId, SpaceId
from iris.features.chat.definition import ResponseGenerationStep, build_response_prompt
from iris.runtime.app import IrisApp
from iris.runtime.conversation import ConversationHistoryPolicy, ShortTermConversationRuntime
from iris.runtime.service import IrisRuntimeService, ObservationEnvelope, RuntimeServiceExtensions
from iris.runtime.state.conversation import InMemoryConversationHistoryStore, conversation_key_for
from iris.runtime.wiring.cognitive import wire_core_cognitive_cycle
from iris.runtime.wiring.llm import wire_response_generator
from tests.helpers.output_pipeline import make_output_pipeline

pytestmark = pytest.mark.anyio


def _record(index: int) -> ConversationRecord:
    role = ConversationRole.USER if index % 2 == 0 else ConversationRole.ASSISTANT
    return ConversationRecord(
        role=role,
        content=f"turn-{index}",
        occurred_at=datetime(2026, 7, 1, tzinfo=UTC) + timedelta(seconds=index),
        observation_id=ObservationId(f"obs-{index}"),
        session_id=SessionId("session-history"),
    )


def _message(text: str) -> ActorMessageObservation:
    return ActorMessageObservation(
        observation_id=ObservationId("obs-current"),
        session_id=SessionId("session-current"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-1"),
                actor_kind=ActorKind.HUMAN,
                display_name="User",
                provider="test",
                provider_subject=ExternalRef("actor-1"),
            ),
            space_id=SpaceId("space-1"),
        ),
        occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )


def test_policy_keeps_recent_records_and_summarizes_older_records() -> None:
    """古いturnはsummaryへ畳み、recent raw recordは分離する。"""
    records = tuple(_record(index) for index in range(6))
    window = ConversationHistoryPolicy(
        max_window_records=2,
        max_history_chars=100,
        summary_enabled=True,
        summary_max_chars=200,
        summary_min_records=3,
    ).build_window(records)

    assert tuple(record.content for record in window.records) == ("turn-4", "turn-5")
    assert window.summary is not None
    assert "turn-0" in window.summary
    assert "turn-5" not in window.summary


def test_policy_does_not_treat_summary_as_raw_record() -> None:
    """Summary は ConversationRecord として混入しない。"""
    records = tuple(_record(index) for index in range(4))
    window = ConversationHistoryPolicy(
        max_window_records=1,
        max_history_chars=100,
        summary_min_records=2,
    ).build_window(records)

    assert len(window.records) == 1
    assert window.records[0].content == "turn-3"
    assert window.summary is not None


async def test_summary_reaches_llm_system_context_not_role_history() -> None:
    """Summary は system internal context に入り、user/assistant message として混ざらない。"""
    llm = FakeLLMClient(responses=("reply",))
    current = _message("current")
    store = InMemoryConversationHistoryStore(max_records=10)
    await store.append(conversation_key_for(current), tuple(_record(index) for index in range(6)))
    app = IrisApp(
        output_pipeline=make_output_pipeline(),
        cycle=wire_core_cognitive_cycle(
            extension_steps=(ResponseGenerationStep(wire_response_generator(llm)),)
        ),
    )
    service = IrisRuntimeService(
        app,
        extensions=RuntimeServiceExtensions(
            conversation_runtime=ShortTermConversationRuntime(
                store,
                policy=ConversationHistoryPolicy(
                    max_window_records=2,
                    max_history_chars=100,
                    summary_enabled=True,
                    summary_max_chars=200,
                    summary_min_records=3,
                ),
            )
        ),
    )

    await service.handle_observation(ObservationEnvelope.external_client(observation=current))

    messages = llm.requests[0].messages
    assert "Conversation summary" not in messages[0].content
    assert "Conversation summary" in messages[1].content
    assert "turn-0" in messages[1].content
    assert tuple(message.content for message in messages[2:]) == ("turn-4", "turn-5", "current")
    assert tuple(message.role for message in messages[2:]) == (
        LLMRole.USER,
        LLMRole.ASSISTANT,
        LLMRole.USER,
    )


def test_frame_builder_preserves_conversation_summary_for_prompt() -> None:
    """SituationContext の summary を WorkspaceFrame と ResponsePrompt へ渡す。"""
    observation = _message("current")
    builder = FrameBuilder()
    frame = builder.build_initial(
        observation,
        situation_context=SituationContextSnapshot(
            conversation_window=ConversationWindow(summary="older summary")
        ),
    )
    frame = builder.apply(
        frame,
        PerceptionResult(
            step_name="perception",
            status=StepStatus.OK,
            text="current",
        ),
    )

    prompt = build_response_prompt(frame)

    assert frame.conversation_summary == "older summary"
    assert prompt is not None
    assert prompt.conversation_summary == "older summary"
