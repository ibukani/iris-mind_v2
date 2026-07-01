"""SQLite baseline schema migration v1。"""

from __future__ import annotations

from iris.adapters.persistence.sqlite.migrator_types import SQLiteMigration

BASELINE_V1 = SQLiteMigration(
    version=1,
    name="baseline_runtime_state",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS accounts (
            account_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            provider_subject TEXT NOT NULL,
            display_name TEXT NOT NULL,
            linked_actor_id TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_accounts_provider_subject
        ON accounts(provider, provider_subject)
        """,
        """
        CREATE TABLE IF NOT EXISTS memories (
            memory_id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            actor_id TEXT,
            space_id TEXT,
            salience REAL NOT NULL DEFAULT 0.0,
            kind TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0,
            source_observation_id TEXT,
            created_at TEXT,
            updated_at TEXT,
            archived INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_memories_actor_id ON memories(actor_id)",
        "CREATE INDEX IF NOT EXISTS idx_memories_space_id ON memories(space_id)",
        "CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind)",
        "CREATE INDEX IF NOT EXISTS idx_memories_archived ON memories(archived)",
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts5 USING fts5(
            text,
            memory_id UNINDEXED
        )
        """,
        """
        INSERT INTO memories_fts5(text, memory_id)
        SELECT memories.text, memories.memory_id
        FROM memories
        WHERE NOT EXISTS (
            SELECT 1 FROM memories_fts5 WHERE memories_fts5.memory_id = memories.memory_id
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS relationship_snapshots (
            actor_id TEXT PRIMARY KEY,
            actor_label TEXT,
            affinity REAL NOT NULL DEFAULT 0.0,
            trust REAL NOT NULL DEFAULT 0.5,
            familiarity REAL NOT NULL DEFAULT 0.0,
            relationship_summary TEXT,
            source_observation_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS affect_baselines (
            owner_key TEXT PRIMARY KEY,
            scope TEXT NOT NULL,
            actor_id TEXT,
            mood_label TEXT,
            valence REAL NOT NULL DEFAULT 0.0,
            arousal REAL NOT NULL DEFAULT 0.0,
            dominance REAL NOT NULL DEFAULT 0.0,
            affect_summary TEXT,
            source_observation_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS activity_events (
            activity_id TEXT PRIMARY KEY,
            source TEXT,
            provider_event_id TEXT,
            actor_id TEXT,
            space_id TEXT,
            activity_kind TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            received_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_events_provider_event
        ON activity_events(source, provider_event_id)
        WHERE source IS NOT NULL AND provider_event_id IS NOT NULL
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_activity_events_occurred_at
        ON activity_events(occurred_at)
        """,
        """
        CREATE TABLE IF NOT EXISTS delivery_outbox (
            delivery_id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            not_before TEXT,
            attempts INTEGER NOT NULL,
            max_attempts INTEGER NOT NULL,
            lease_id TEXT,
            lease_expires_at TEXT,
            blocked_reason TEXT,
            last_error_reason TEXT,
            source_observation_id TEXT,
            target_provider TEXT NOT NULL,
            target_provider_subject TEXT,
            target_provider_space_ref TEXT,
            target_session_id TEXT NOT NULL,
            target_actor_id TEXT,
            target_account_id TEXT,
            target_space_id TEXT,
            action_type TEXT NOT NULL,
            action_id TEXT NOT NULL,
            action_session_id TEXT NOT NULL,
            action_correlation_id TEXT NOT NULL,
            action_text TEXT NOT NULL
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_outbox_idempotency_key
        ON delivery_outbox(idempotency_key)
        """,
        """
        CREATE INDEX IF NOT EXISTS delivery_outbox_due_idx
        ON delivery_outbox(target_provider, status, created_at, delivery_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS delivery_report_fingerprints (
            fingerprint_key TEXT PRIMARY KEY,
            delivery_id TEXT NOT NULL REFERENCES delivery_outbox(delivery_id) ON DELETE CASCADE,
            lease_id TEXT,
            action_id TEXT NOT NULL,
            correlation_id TEXT NOT NULL,
            status TEXT NOT NULL,
            external_message_id TEXT,
            error_reason TEXT
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS delivery_report_lease_idx
        ON delivery_report_fingerprints(delivery_id, lease_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS scheduler_targets (
            provider TEXT NOT NULL,
            provider_subject TEXT NOT NULL,
            provider_space_ref TEXT NOT NULL,
            session_id TEXT NOT NULL,
            actor_id TEXT,
            account_id TEXT,
            space_id TEXT,
            display_name TEXT,
            last_observed_at TEXT NOT NULL,
            last_scheduler_attempt_at TEXT,
            stale_after TEXT,
            route_display_name TEXT,
            PRIMARY KEY (provider, provider_subject, provider_space_ref, session_id)
        )
        """,
    ),
)
