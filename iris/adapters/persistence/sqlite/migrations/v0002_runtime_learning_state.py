"""SQLite runtime learning durable state migration v2。"""

from __future__ import annotations

from iris.adapters.persistence.sqlite.migrator_types import SQLiteMigration

RUNTIME_LEARNING_STATE_V2 = SQLiteMigration(
    version=2,
    name="runtime_learning_state",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS background_jobs (
            job_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            payload_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL,
            max_attempts INTEGER NOT NULL,
            not_before TEXT NOT NULL,
            leased_until TEXT,
            idempotency_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_error TEXT
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_background_jobs_due
        ON background_jobs(status, not_before, created_at, job_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_background_jobs_kind_status
        ON background_jobs(kind, status, created_at, job_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS memory_candidate_reviews (
            candidate_id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            candidate_json TEXT NOT NULL,
            candidate_text TEXT NOT NULL,
            candidate_kind TEXT NOT NULL,
            candidate_source TEXT NOT NULL,
            candidate_reason TEXT,
            candidate_confidence REAL NOT NULL,
            candidate_salience REAL NOT NULL,
            candidate_retention_policy TEXT NOT NULL,
            candidate_sensitivity TEXT NOT NULL,
            candidate_review_required INTEGER NOT NULL,
            actor_id TEXT,
            account_id TEXT,
            space_id TEXT,
            source_observation_id TEXT,
            reviewed_at TEXT,
            reviewed_by TEXT,
            review_reason TEXT,
            promoted_memory_id TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_memory_candidate_reviews_status_created
        ON memory_candidate_reviews(status, created_at, candidate_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_memory_candidate_reviews_actor_status
        ON memory_candidate_reviews(actor_id, status, created_at, candidate_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_memory_candidate_reviews_account_status
        ON memory_candidate_reviews(account_id, status, created_at, candidate_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_memory_candidate_reviews_space_status
        ON memory_candidate_reviews(space_id, status, created_at, candidate_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_memory_candidate_reviews_source_observation
        ON memory_candidate_reviews(source_observation_id)
        """,
    ),
)
