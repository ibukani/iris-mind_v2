"""SQLite background_jobs schema contract。"""

from __future__ import annotations

BACKGROUND_JOBS_TABLE = "background_jobs"
BACKGROUND_JOB_REQUIRED_COLUMNS = frozenset(
    {
        "job_id",
        "kind",
        "payload_type",
        "payload_json",
        "status",
        "attempts",
        "max_attempts",
        "not_before",
        "resource_profile_json",
        "leased_until",
        "idempotency_key",
        "created_at",
        "updated_at",
        "last_error",
        "defer_reason",
    }
)
