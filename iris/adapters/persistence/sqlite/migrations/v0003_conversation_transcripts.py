"""SQLite conversation transcript state migration v3。"""

from __future__ import annotations

from iris.adapters.persistence.sqlite.migrator_types import SQLiteMigration

CONVERSATION_TRANSCRIPTS_V3 = SQLiteMigration(
    version=3,
    name="conversation_transcripts",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS conversation_transcripts (
            transcript_id TEXT PRIMARY KEY,
            subject_kind TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            space_id TEXT,
            session_id TEXT NOT NULL,
            actor_id TEXT,
            account_id TEXT,
            observation_id TEXT,
            role TEXT NOT NULL,
            source TEXT NOT NULL,
            content TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            retention_until TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_conversation_transcripts_key_time
        ON conversation_transcripts(subject_kind, subject_id, space_id, occurred_at, transcript_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_conversation_transcripts_account_time
        ON conversation_transcripts(account_id, occurred_at, transcript_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_conversation_transcripts_actor_time
        ON conversation_transcripts(actor_id, occurred_at, transcript_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_conversation_transcripts_session_time
        ON conversation_transcripts(session_id, occurred_at, transcript_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_conversation_transcripts_retention
        ON conversation_transcripts(retention_until)
        """,
    ),
)
