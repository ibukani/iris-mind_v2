"""短期会話履歴storeとruntime統合のテスト。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.ports import LLMRole
from iris.contracts.actions import PresentedOutput
from iris.contracts.conversation import ConversationRecord, ConversationRole
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import AccountId, ActorId, ExternalRef, ObservationId, SessionId, SpaceId
from iris.features.chat.definition import ResponseGenerationStep
from iris.runtime.app import IrisApp
from iris.runtime.conversation import ShortTermConversationRuntime
from iris.runtime.service import IrisRuntimeService, ObservationEnvelope
from iris.runtime.state.conversation import (
    ConversationKey,
    ConversationSubjectKind,
    InMemoryConversationHistoryStore,
    conversation_key_for,
)
from iris.runtime.wiring.cognitive import wire_core_cognitive_cycle
from iris.runtime.wiring.llm import wire_response_generator
from tests.helpers.output_pipeline import make_output_pipeline

pytestmark = pytest.mark.anyio


def _record(content: str, offset: int = 0) -> ConversationRecord:
    now = datetime(2026, 6, 30, tzinfo=UTC) + timedelta(seconds=offset)
    return ConversationRecord(
        role=ConversationRole.USER,
        content=content,
        occurred_at=now,
        observation_id=ObservationId(f"obs-{offset}"),
        session_id=SessionId(f"session-{offset}"),
    )


def _message(
    text: str,
    *,
    observation_id: str,
    session_id: str,
    actor_id: str = "actor-1",
    space_id: str = "space-1",
) -> ActorMessageObservation:
    return ActorMessageObservation(
        observation_id=ObservationId(observation_id),
        session_id=SessionId(session_id),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId(actor_id),
                actor_kind=ActorKind.HUMAN,
                display_name="User",
                provider="test",
                provider_subject=ExternalRef(actor_id),
            ),
            space_id=SpaceId(space_id),
        ),
        occurred_at=datetime(2026, 6, 30, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )


async def test_store_returns_chronological_limited_windows_without_key_leakage() -> None:
    """Storeはkeyを分離し、直近limit件を時系列順で返す。"""
    store = InMemoryConversationHistoryStore(max_records=3)
    first_key = ConversationKey(ConversationSubjectKind.ACTOR, "actor-1", "space-1")
    other_key = ConversationKey(ConversationSubjectKind.ACTOR, "actor-2", "space-1")
    await store.append(first_key, tuple(_record(str(index), index) for index in range(4)))
    await store.append(other_key, (_record("other"),))

    window = await store.recent_window(first_key, 2)
    assert tuple(record.content for record in window.records) == ("2", "3")
    assert tuple(
        record.content for record in (await store.recent_window(other_key, 5)).records
    ) == ("other",)


async def test_runtime_history_uses_actor_and_space_across_session_changes() -> None:
    """異なるsessionでも同一actor/spaceの前ターンをLLMへ渡す。"""
    llm = FakeLLMClient(responses=("最初の返答", "二回目の返答"))
    app = IrisApp(
        output_pipeline=make_output_pipeline(),
        cycle=wire_core_cognitive_cycle(
            extension_steps=(ResponseGenerationStep(wire_response_generator(llm)),)
        ),
    )
    history_store = InMemoryConversationHistoryStore()
    service = IrisRuntimeService(
        app,
        conversation_runtime=ShortTermConversationRuntime(history_store),
    )
    first = _message(
        "最初の質問",
        observation_id="obs-first",
        session_id="session-first",
    )
    second = _message(
        "続きの質問",
        observation_id="obs-second",
        session_id="session-second",
    )

    await service.handle_observation(ObservationEnvelope.external_client(observation=first))
    await service.handle_observation(ObservationEnvelope.external_client(observation=second))

    messages = llm.requests[1].messages
    assert tuple((message.role, message.content) for message in messages[1:]) == (
        (LLMRole.USER, "最初の質問"),
        (LLMRole.ASSISTANT, "最初の返答"),
        (LLMRole.USER, "続きの質問"),
    )
    assert sum(message.content == "続きの質問" for message in messages) == 1
    assert conversation_key_for(first) == conversation_key_for(second)


async def test_different_actor_or_space_does_not_share_history() -> None:
    """Actorまたはspaceが異なる会話へ履歴を漏らさない。"""
    store = InMemoryConversationHistoryStore()
    runtime = ShortTermConversationRuntime(store)
    first = _message("secret", observation_id="obs-1", session_id="s-1")
    await runtime.record_response(first, PresentedOutput(text="reply"))
    other_actor = _message(
        "new",
        observation_id="obs-2",
        session_id="s-2",
        actor_id="actor-2",
    )
    other_space = _message(
        "new",
        observation_id="obs-3",
        session_id="s-3",
        space_id="space-2",
    )
    assert not (await runtime.load_context(other_actor, None)).conversation_window.records
    assert not (await runtime.load_context(other_space, None)).conversation_window.records


async def test_empty_output_does_not_record_turn() -> None:
    """No-action相当の空出力はuser/assistant履歴を追加しない。"""
    store = InMemoryConversationHistoryStore()
    runtime = ShortTermConversationRuntime(store)
    observation = _message("ignored", observation_id="obs-empty", session_id="s-empty")
    await runtime.record_response(observation, PresentedOutput(text=None))
    assert not (await store.recent_window(conversation_key_for(observation), 10)).records


def test_conversation_key_prefers_account_then_falls_back_to_session() -> None:
    """Actor不在時はaccount、identity不在時だけsessionを使う。"""
    account_observation = ActorMessageObservation(
        observation_id=ObservationId("obs-account"),
        session_id=SessionId("session-account"),
        context=ObservationContext(
            account_id=AccountId("account-1"),
            space_id=SpaceId("space-1"),
        ),
        occurred_at=datetime(2026, 6, 30, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="account turn",
    )
    fallback_observation = ActorMessageObservation(
        observation_id=ObservationId("obs-fallback"),
        session_id=SessionId("session-fallback"),
        context=ObservationContext(space_id=SpaceId("space-ignored")),
        occurred_at=datetime(2026, 6, 30, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="fallback turn",
    )
    assert conversation_key_for(account_observation) == ConversationKey(
        ConversationSubjectKind.ACCOUNT,
        "account-1",
        "space-1",
    )
    assert conversation_key_for(fallback_observation) == ConversationKey(
        ConversationSubjectKind.SESSION,
        "session-fallback",
    )
