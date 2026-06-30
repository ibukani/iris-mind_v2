"""短期会話履歴storeとruntime統合のテスト。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.ports import LLMRole
from iris.contracts.actions import PresentedOutput
from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.contracts.conversation import ConversationRecord, ConversationRole
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.contracts.workspace_context import SituationContextSnapshot
from iris.core.ids import AccountId, ActorId, ExternalRef, ObservationId, SessionId, SpaceId
from iris.features.chat.definition import ResponseGenerationStep
from iris.runtime.app import IrisApp
from iris.runtime.conversation import ConversationHistoryPolicy, ShortTermConversationRuntime
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
    account_id: str | None = None,
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
            account_id=AccountId(account_id) if account_id is not None else None,
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


def test_history_policy_applies_record_limit() -> None:
    """Policyはstore上限とは別にLLM window件数を制限する。"""
    records = tuple(_record(str(index), index) for index in range(4))
    trimmed = ConversationHistoryPolicy(
        max_window_records=2,
        max_history_chars=100,
    ).trim(records)
    assert tuple(record.content for record in trimmed) == ("2", "3")


def test_history_policy_removes_older_records_before_newer_records() -> None:
    """文字budget超過時は古いrecordから除外する。"""
    records = (_record("old", 1), _record("recent", 2), _record("new", 3))
    trimmed = ConversationHistoryPolicy(
        max_window_records=10,
        max_history_chars=9,
    ).trim(records)
    assert tuple(record.content for record in trimmed) == ("recent", "new")


@pytest.mark.parametrize("budget", [0, -1])
def test_history_policy_disables_history_for_non_positive_budget(budget: int) -> None:
    """Zero/negative文字budgetでは過去会話を渡さない。"""
    assert ConversationHistoryPolicy(max_history_chars=budget).trim((_record("past"),)) == ()


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


async def test_runtime_history_messages_respect_character_budget() -> None:
    """LLMへ変換された過去message内容が設定文字budgetを超えない。"""
    llm = FakeLLMClient(responses=("reply",))
    app = IrisApp(
        output_pipeline=make_output_pipeline(),
        cycle=wire_core_cognitive_cycle(
            extension_steps=(ResponseGenerationStep(wire_response_generator(llm)),)
        ),
    )
    store = InMemoryConversationHistoryStore()
    current = _message("current", observation_id="obs-current", session_id="session-current")
    await store.append(
        conversation_key_for(current),
        (_record("older-long", 1), _record("recent", 2)),
    )
    service = IrisRuntimeService(
        app,
        conversation_runtime=ShortTermConversationRuntime(
            store,
            policy=ConversationHistoryPolicy(max_window_records=10, max_history_chars=6),
        ),
    )
    await service.handle_observation(ObservationEnvelope.external_client(observation=current))
    prior_messages = llm.requests[0].messages[1:-1]
    assert tuple(message.content for message in prior_messages) == ("recent",)
    assert sum(len(message.content) for message in prior_messages) <= 6
    assert sum(message.content == "current" for message in llm.requests[0].messages) == 1


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


async def test_load_context_preserves_existing_snapshot_fields() -> None:
    """Conversation window差替え時に既存situation fieldを保持する。"""
    now = datetime(2026, 6, 30, tzinfo=UTC)
    availability = AvailabilitySnapshot(
        actor_id=ActorId("actor-1"),
        status=AvailabilityStatus.AVAILABLE,
        reason="test",
        observed_at=now,
        computed_at=now,
    )
    observation = _message("current", observation_id="obs-context", session_id="s-context")
    runtime = ShortTermConversationRuntime(InMemoryConversationHistoryStore())
    updated = await runtime.load_context(
        observation,
        SituationContextSnapshot(availability=availability),
    )
    assert updated.availability == availability


def test_conversation_key_priority_is_actor_then_account_then_session() -> None:
    """Actorを最優先し、account、sessionの順でfallbackする。"""
    actor_and_account = _message(
        "actor turn",
        observation_id="obs-actor-account",
        session_id="session-actor-account",
        account_id="account-ignored",
    )
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
    assert conversation_key_for(actor_and_account) == ConversationKey(
        ConversationSubjectKind.ACTOR,
        "actor-1",
        "space-1",
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
