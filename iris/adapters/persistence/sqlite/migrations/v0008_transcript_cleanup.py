"""SQLite transcript cleanup operation migration v8。"""

from __future__ import annotations

from iris.adapters.persistence.sqlite.migrator_types import SQLiteMigration

TRANSCRIPT_CLEANUP_V8 = SQLiteMigration(
    version=8,
    name="transcript_cleanup",
    statements=(
        """
        ALTER TABLE conversation_transcripts
        ADD COLUMN legal_hold_until TEXT
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_conversation_transcripts_legal_hold
        ON conversation_transcripts(legal_hold_until)
        """,
        """
        CREATE TABLE IF NOT EXISTS transcript_cleanup_operations (
            operation_id TEXT PRIMARY KEY,
            request_fingerprint TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
    ),
)
