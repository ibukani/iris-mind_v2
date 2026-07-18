"""Presentation hints永続化migration。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.persistence.sqlite.migrator_types import SQLiteMigration

if TYPE_CHECKING:
    import sqlite3


def _presentation_hints_column_exists(conn: sqlite3.Connection) -> bool:
    """未versioned SQLAlchemy schemaが新列を先に作ったか確認する。

    Returns:
        新列が既に存在する場合はTrue。
    """
    row = conn.execute(
        """
        SELECT 1
        FROM pragma_table_info('delivery_outbox')
        WHERE name = 'action_presentation_hints_json'
        LIMIT 1
        """
    ).fetchone()
    return row is not None


PRESENTATION_HINTS_V7 = SQLiteMigration(
    version=7,
    name="presentation_hints",
    statements=("ALTER TABLE delivery_outbox ADD COLUMN action_presentation_hints_json TEXT",),
    skip_if=_presentation_hints_column_exists,
)
