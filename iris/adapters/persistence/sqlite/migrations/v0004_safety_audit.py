"""SQLite durable safety audit migration v4。"""

from __future__ import annotations

from iris.adapters.persistence.sqlite.migrator_types import SQLiteMigration

SAFETY_AUDIT_V4 = SQLiteMigration(
    version=4,
    name="safety_audit_records",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS safety_audit_records (
            audit_id TEXT PRIMARY KEY,
            observation_id TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            stage TEXT NOT NULL,
            allowed INTEGER NOT NULL,
            reason TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            source TEXT NOT NULL,
            target_key TEXT NOT NULL,
            policy TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            retention_until TEXT
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_safety_audit_target_stage_allowed_time
        ON safety_audit_records(target_key, stage, allowed, occurred_at)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_safety_audit_occurred_at
        ON safety_audit_records(occurred_at)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_safety_audit_retention
        ON safety_audit_records(retention_until)
        """,
    ),
)
