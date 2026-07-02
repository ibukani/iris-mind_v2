"""SQLite transcript schema contract。"""

from __future__ import annotations

CONVERSATION_TRANSCRIPTS_TABLE = "conversation_transcripts"
CONVERSATION_TRANSCRIPT_REQUIRED_COLUMNS = frozenset(
    {
        "transcript_id",
        "subject_kind",
        "subject_id",
        "space_id",
        "session_id",
        "actor_id",
        "account_id",
        "observation_id",
        "role",
        "source",
        "content",
        "occurred_at",
        "recorded_at",
        "retention_until",
        "metadata_json",
    }
)
