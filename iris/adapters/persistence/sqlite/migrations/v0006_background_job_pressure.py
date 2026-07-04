"""SQLite migration v6: background job pressure metadata。"""

from __future__ import annotations

from iris.adapters.persistence.sqlite.migrator_types import SQLiteMigration

BACKGROUND_JOB_PRESSURE_V6 = SQLiteMigration(
    version=6,
    name="background_job_pressure",
    statements=(
        """
        ALTER TABLE background_jobs
        ADD COLUMN resource_profile_json TEXT NOT NULL
        DEFAULT '{"uses_llm":false,"idle_only":false,"model_call_descriptor":null}'
        """,
        """
        ALTER TABLE background_jobs
        ADD COLUMN defer_reason TEXT
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_background_jobs_kind_status_not_before
        ON background_jobs(kind, status, not_before)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_background_jobs_non_terminal
        ON background_jobs(status, kind, leased_until)
        WHERE status IN ('pending', 'failed_retryable', 'leased')
        """,
    ),
)
