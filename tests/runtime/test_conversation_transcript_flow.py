"""Conversation transcript runtime flow tests。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.contracts.actions import ActionResult, ActionStatus, PresentedOutput, SendMessageAction
from iris.contracts.conversation import ConversationRole
from iris.contracts.delivery import DeliveryTarget
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.learning import LearningEvent
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.contracts.transcript import (
    TranscriptPruneResult,
    TranscriptQuery,
    TranscriptRecord,
    TranscriptRole,
    TranscriptSource,
    TranscriptSubjectKind,
)
from iris.core.ids import (
    AccountId,
    ActionId,
    ActorId,
    CorrelationId,
    ExternalRef,
    ObservationId,
    SessionId,
    SpaceId,
)
from iris.runtime.conversation import DeliveryConversationHistoryHook, ShortTermConversationRuntime
from iris.runtime.state.conversation import (
    InMemoryConversationHistoryStore,
    conversation_key_for,
    conversation_key_for_delivery_target,
)
from tests.helpers.transcript import InMemoryTranscriptStore

pytestmark = pytest.mark.anyio


class TranscriptUnavailableError(RuntimeError):
    """Test double 用 transcript failure。"""


class FailingTranscriptStore:
    """Transcript append failure isolation 用の test double。"""

    async def append(self, records: tuple[TranscriptRecord, ...]) -> None:
        """常に transcript write failure を起こす。

        Raises:
            TranscriptUnavailableError: transcript store failure を模倣する。
        """
        _ = records
        message = "transcript unavailable"
        raise TranscriptUnavailableError(message)

    async def query(self, query: TranscriptQuery) -> tuple[TranscriptRecord, ...]:
        """Failure isolation test では空集合を返す。

        Returns:
            空の transcript record 集合。
        """
        _ = query
        return ()

    async def prune_expired(self, now: datetime) -> TranscriptPruneResult:
        """Failure isolation test では削除なしを返す。

        Returns:
            削除件数 0。
        """
        _ = now
        return TranscriptPruneResult(deleted_count=0)


def _message(text: str, *, space_id: str = "space-1") -> ActorMessageObservation:
    return ActorMessageObservation(
        observation_id=ObservationId("obs-inline"),
        session_id=SessionId("session-inline"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-1"),
                actor_kind=ActorKind.HUMAN,
                display_name="User",
                provider="test",
                provider_subject=ExternalRef("actor-1"),
            ),
            space_id=SpaceId(space_id),
        ),
        occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )


def _account_message(
    text: str,
    *,
    account_id: str = "account-1",
    space_id: str = "space-1",
    session_id: str = "session-account",
) -> ActorMessageObservation:
    return ActorMessageObservation(
        observation_id=ObservationId(f"obs-{session_id}"),
        session_id=SessionId(session_id),
        context=ObservationContext(
            account_id=AccountId(account_id),
            space_id=SpaceId(space_id),
        ),
        occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )


def _session_message(
    text: str,
    *,
    session_id: str = "session-fallback",
    space_id: str = "space-ignored",
) -> ActorMessageObservation:
    return ActorMessageObservation(
        observation_id=ObservationId(f"obs-{session_id}"),
        session_id=SessionId(session_id),
        context=ObservationContext(space_id=SpaceId(space_id)),
        occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )


def _delivery_event(
    status: ActionStatus,
    *,
    action_id: str = "action-delivery",
    text: str = "delivered reply",
) -> LearningEvent:
    reported_at = datetime(2026, 7, 1, 0, 0, 5, tzinfo=UTC)
    action = SendMessageAction(
        action_id=ActionId(action_id),
        session_id=SessionId("session-delivery"),
        correlation_id=CorrelationId("corr-delivery"),
        text=text,
    )
    return LearningEvent(
        result=ActionResult(
            action_id=action.action_id,
            correlation_id=action.correlation_id,
            status=status,
            delivered_at=reported_at if status is ActionStatus.SUCCEEDED else None,
        ),
        delivery=None,
        action=action,
        target=DeliveryTarget(
            provider="discord",
            provider_subject=ExternalRef("actor-1"),
            provider_space_ref=ExternalRef("space-1"),
            session_id=SessionId("session-delivery"),
            actor_id=ActorId("actor-1"),
            space_id=SpaceId("space-1"),
        ),
        reported_at=reported_at,
        source_observation_id=ObservationId("obs-delivery"),
    )


async def test_inline_sendable_response_writes_confirmed_transcript() -> None:
    """Inline response は短期履歴と transcript の両方に user/assistant turn を残す。"""
    history = InMemoryConversationHistoryStore()
    transcript = InMemoryTranscriptStore()
    runtime = ShortTermConversationRuntime(history, transcript_store=transcript)
    observation = _message("hello")

    await runtime.record_response(observation, PresentedOutput(text="reply"))

    window = await history.recent_window(conversation_key_for(observation), 10)
    records = await transcript.query(TranscriptQuery(actor_id=ActorId("actor-1")))
    assert tuple(record.role for record in window.records) == (
        ConversationRole.USER,
        ConversationRole.ASSISTANT,
    )
    assert tuple(record.role for record in records) == (
        TranscriptRole.USER,
        TranscriptRole.ASSISTANT,
    )
    assert {record.source for record in records} == {TranscriptSource.INLINE_RESPONSE}


async def test_unsendable_inline_response_does_not_write_transcript() -> None:
    """No-action 相当の output は transcript に入れない。"""
    transcript = InMemoryTranscriptStore()
    runtime = ShortTermConversationRuntime(
        InMemoryConversationHistoryStore(),
        transcript_store=transcript,
    )

    await runtime.record_response(_message("hello"), PresentedOutput(text=None))

    assert await transcript.query(TranscriptQuery(actor_id=ActorId("actor-1"))) == ()


@pytest.mark.parametrize(
    "status",
    [ActionStatus.BLOCKED, ActionStatus.FAILED, ActionStatus.CANCELLED],
)
async def test_delivery_unsuccessful_results_do_not_write_transcript(
    status: ActionStatus,
) -> None:
    """Blocked/failed/cancelled delivery は normal transcript に入れない。"""
    transcript = InMemoryTranscriptStore()
    hook = DeliveryConversationHistoryHook(
        InMemoryConversationHistoryStore(),
        transcript_store=transcript,
    )

    await hook.after_action_result(_delivery_event(status))

    assert await transcript.query(TranscriptQuery(actor_id=ActorId("actor-1"))) == ()


async def test_delivery_success_writes_transcript() -> None:
    """Delivery result は成功時だけ confirmed transcript へ反映する。"""
    transcript = InMemoryTranscriptStore()
    hook = DeliveryConversationHistoryHook(
        InMemoryConversationHistoryStore(),
        transcript_store=transcript,
    )

    await hook.after_action_result(_delivery_event(ActionStatus.SUCCEEDED))

    records = await transcript.query(TranscriptQuery(actor_id=ActorId("actor-1")))
    assert tuple(record.content for record in records) == ("delivered reply",)
    assert records[0].source is TranscriptSource.DELIVERED_ACTION


async def test_delivery_transcript_ids_do_not_collapse_distinct_same_timestamp_outputs() -> None:
    """同一timestamp/sourceでも別actionのdelivery turnは別transcriptとして残す。"""
    transcript = InMemoryTranscriptStore()
    hook = DeliveryConversationHistoryHook(
        InMemoryConversationHistoryStore(),
        transcript_store=transcript,
    )

    await hook.after_action_result(
        _delivery_event(ActionStatus.SUCCEEDED, action_id="action-a", text="same reply")
    )
    await hook.after_action_result(
        _delivery_event(ActionStatus.SUCCEEDED, action_id="action-b", text="same reply")
    )

    records = await transcript.query(TranscriptQuery(actor_id=ActorId("actor-1")))

    assert tuple(record.content for record in records) == ("same reply", "same reply")
    assert tuple(record.metadata["action_id"] for record in records) == (
        "action-a",
        "action-b",
    )
    assert len({record.transcript_id for record in records}) == 2


async def test_transcript_isolated_by_space() -> None:
    """Transcript も actor/space 境界を越えて漏らさない。"""
    transcript = InMemoryTranscriptStore()
    runtime = ShortTermConversationRuntime(
        InMemoryConversationHistoryStore(),
        transcript_store=transcript,
    )
    await runtime.record_response(
        _message("secret", space_id="space-1"),
        PresentedOutput(text="reply"),
    )

    records = await transcript.query(
        TranscriptQuery(actor_id=ActorId("actor-1"), space_id=SpaceId("space-2"))
    )

    assert records == ()


async def test_account_fallback_transcript_is_isolated_by_space() -> None:
    """Actor未解決時の account transcript も space 境界で分離する。"""
    transcript = InMemoryTranscriptStore()
    runtime = ShortTermConversationRuntime(
        InMemoryConversationHistoryStore(),
        transcript_store=transcript,
    )

    await runtime.record_response(
        _account_message("account secret", space_id="space-1"),
        PresentedOutput(text="account reply"),
    )

    same_space = await transcript.query(
        TranscriptQuery(
            subject_kind=TranscriptSubjectKind.ACCOUNT,
            subject_id="account-1",
            space_id=SpaceId("space-1"),
        )
    )
    other_space = await transcript.query(
        TranscriptQuery(
            subject_kind=TranscriptSubjectKind.ACCOUNT,
            subject_id="account-1",
            space_id=SpaceId("space-2"),
        )
    )

    assert tuple(record.content for record in same_space) == (
        "account secret",
        "account reply",
    )
    assert other_space == ()


async def test_session_fallback_transcript_is_used_only_without_actor_or_account() -> None:
    """Actor/account未解決時だけ session subject へ fallback する。"""
    transcript = InMemoryTranscriptStore()
    runtime = ShortTermConversationRuntime(
        InMemoryConversationHistoryStore(),
        transcript_store=transcript,
    )

    await runtime.record_response(
        _session_message("session-only"),
        PresentedOutput(text="session reply"),
    )

    records = await transcript.query(
        TranscriptQuery(
            subject_kind=TranscriptSubjectKind.SESSION,
            subject_id="session-fallback",
        )
    )

    assert tuple(record.content for record in records) == ("session-only", "session reply")
    assert {record.actor_id for record in records} == {None}
    assert {record.account_id for record in records} == {None}


async def test_inline_transcript_ids_are_idempotent_for_reprocessed_observation() -> None:
    """同一 observation の再処理は content / timestamp 変化で transcript ID を増やさない。"""
    transcript = InMemoryTranscriptStore()
    timestamps = iter(
        (
            datetime(2026, 7, 1, 0, 0, 1, tzinfo=UTC),
            datetime(2026, 7, 1, 0, 0, 9, tzinfo=UTC),
        )
    )
    runtime = ShortTermConversationRuntime(
        InMemoryConversationHistoryStore(),
        transcript_store=transcript,
        now=lambda: next(timestamps),
    )
    observation = _message("same user input")

    await runtime.record_response(observation, PresentedOutput(text="first reply"))
    await runtime.record_response(observation, PresentedOutput(text="changed reply"))

    records = await transcript.query(TranscriptQuery(actor_id=ActorId("actor-1")))

    assert tuple(record.content for record in records) == (
        "same user input",
        "first reply",
        "same user input",
        "changed reply",
    )
    assert records[0].transcript_id == records[2].transcript_id
    assert records[1].transcript_id == records[3].transcript_id


async def test_inline_transcript_failure_does_not_fail_response_recording() -> None:
    """Transcript 書き込み失敗は inline response path を失敗させない。"""
    history = InMemoryConversationHistoryStore()
    observation = _message("hello")
    runtime = ShortTermConversationRuntime(
        history,
        transcript_store=FailingTranscriptStore(),
    )

    await runtime.record_response(observation, PresentedOutput(text="reply"))

    window = await history.recent_window(conversation_key_for(observation), 10)
    assert tuple(record.role for record in window.records) == (
        ConversationRole.USER,
        ConversationRole.ASSISTANT,
    )


async def test_delivery_transcript_failure_does_not_fail_history_confirmation() -> None:
    """Transcript 書き込み失敗は delivery confirmed history を失敗させない。"""
    history = InMemoryConversationHistoryStore()
    hook = DeliveryConversationHistoryHook(
        history,
        transcript_store=FailingTranscriptStore(),
    )
    event = _delivery_event(ActionStatus.SUCCEEDED)

    await hook.after_action_result(event)

    target = event.target
    assert target is not None
    window = await history.recent_window(
        conversation_key_for_delivery_target(target),
        10,
    )
    assert tuple(record.content for record in window.records) == ("delivered reply",)
