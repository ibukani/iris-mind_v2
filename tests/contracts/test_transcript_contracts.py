"""Transcript contract tests。"""

from __future__ import annotations

from datetime import UTC, datetime

from iris.contracts.conversation import ConversationRecord, ConversationRole
from iris.contracts.transcript import (
    TranscriptDeletionPolicy,
    TranscriptRecord,
    TranscriptRetentionPolicy,
    TranscriptRole,
    TranscriptSource,
    TranscriptSubjectKind,
)
from iris.core.ids import ObservationId, SessionId, TranscriptId


def test_transcript_record_is_separate_from_short_term_conversation_record() -> None:
    """TranscriptRecord は短期 ConversationRecord と別 contract として扱う。"""
    occurred_at = datetime(2026, 7, 1, tzinfo=UTC)
    conversation = ConversationRecord(
        role=ConversationRole.USER,
        content="short-term only",
        occurred_at=occurred_at,
        observation_id=ObservationId("obs-1"),
        session_id=SessionId("session-1"),
    )
    transcript = TranscriptRecord(
        transcript_id=TranscriptId("tr-1"),
        subject_kind=TranscriptSubjectKind.SESSION,
        subject_id="session-1",
        role=TranscriptRole.USER,
        source=TranscriptSource.INLINE_RESPONSE,
        content="durable transcript",
        occurred_at=occurred_at,
        recorded_at=occurred_at,
        session_id=SessionId("session-1"),
    )

    assert "transcript_id" not in ConversationRecord.model_fields
    assert "transcript_id" in TranscriptRecord.model_fields
    assert transcript.transcript_id == TranscriptId("tr-1")
    assert transcript.content != conversation.content


def test_transcript_retention_policy_defaults_to_bounded_storage() -> None:
    """Transcript retention は opt-in storage でも既定で期限付きにする。"""
    policy = TranscriptRetentionPolicy()

    assert policy.retention_days == 30


def test_transcript_deletion_policy_does_not_delete_other_state_by_default() -> None:
    """Transcript deletion は memory / review / delivery state へ暗黙伝搬しない。"""
    policy = TranscriptDeletionPolicy()

    assert policy.delete_transcript_records
    assert not policy.delete_canonical_memory
    assert not policy.delete_review_candidates
    assert not policy.delete_delivery_state
