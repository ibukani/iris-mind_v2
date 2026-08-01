"""SQLite delivery user control / safety audit model versions migration v9。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.persistence.sqlite.migrator_types import SQLiteMigration

if TYPE_CHECKING:
    import sqlite3


def _safety_audit_model_versions_column_exists(conn: sqlite3.Connection) -> bool:
    """未versioned SQLAlchemy schemaが新列を先に作ったか確認する。

    Returns:
        新列が既に存在する場合はTrue。
    """
    row = conn.execute(
        """
        SELECT 1
        FROM pragma_table_info('safety_audit_records')
        WHERE name = 'model_versions'
        LIMIT 1
        """
    ).fetchone()
    return row is not None


DELIVERY_USER_CONTROL_AND_AUDIT_VERSIONS_V9 = SQLiteMigration(
    version=9,
    name="delivery_user_controls_and_audit_model_versions",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS delivery_user_controls (
            target_key TEXT PRIMARY KEY,
            opt_out INTEGER NOT NULL,
            muted INTEGER NOT NULL,
            blocked INTEGER NOT NULL,
            interruptions_allowed INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        ALTER TABLE safety_audit_records
        ADD COLUMN model_versions TEXT NOT NULL DEFAULT ''
        """,
    ),
    skip_if=_safety_audit_model_versions_column_exists,
)
