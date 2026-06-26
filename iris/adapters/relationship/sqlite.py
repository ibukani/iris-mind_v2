"""SQLite-backed relationship state store。"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING, override

from iris.contracts.relationship import RelationshipSnapshotRecord, RelationshipStore
from iris.core.datetime_utils import now_utc, parse_datetime
from iris.core.ids import ActorId, ObservationId

if TYPE_CHECKING:
    from collections.abc import Generator


class SQLiteRelationshipStore(RelationshipStore):
    """ActorId を主キーにした SQLite relationship state store。"""

    def __init__(self, db_path: str | Path) -> None:
        """SQLite DB path を受け取り、必要な table を作成する。"""
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS relationship_snapshots (
                    actor_id TEXT PRIMARY KEY,
                    actor_label TEXT,
                    affinity REAL NOT NULL,
                    trust REAL NOT NULL,
                    familiarity REAL NOT NULL,
                    relationship_summary TEXT,
                    source_observation_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    CHECK (affinity >= -1.0 AND affinity <= 1.0),
                    CHECK (trust >= 0.0 AND trust <= 1.0),
                    CHECK (familiarity >= 0.0 AND familiarity <= 1.0),
                    CHECK (version >= 1)
                )
                """,
            )

    @override
    def get(self, actor_id: ActorId) -> RelationshipSnapshotRecord | None:
        """ActorId に対応する relationship state を取得する。

        Returns:
            保存済み record。存在しない場合は None。
        """
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT
                    actor_id,
                    actor_label,
                    affinity,
                    trust,
                    familiarity,
                    relationship_summary,
                    source_observation_id,
                    created_at,
                    updated_at,
                    version
                FROM relationship_snapshots
                WHERE actor_id = ?
                """,
                (str(actor_id),),
            ).fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    @override
    def upsert(
        self,
        record: RelationshipSnapshotRecord,
    ) -> RelationshipSnapshotRecord:
        """Relationship state を upsert して保存後の record を返す。

        Returns:
            保存後の RelationshipSnapshotRecord。
        """
        now = now_utc()
        current = self.get(record.actor_id)
        stored = replace(
            record,
            created_at=current.created_at if current else record.created_at or now,
            updated_at=now,
        )
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO relationship_snapshots (
                    actor_id,
                    actor_label,
                    affinity,
                    trust,
                    familiarity,
                    relationship_summary,
                    source_observation_id,
                    created_at,
                    updated_at,
                    version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(actor_id) DO UPDATE SET
                    actor_label = excluded.actor_label,
                    affinity = excluded.affinity,
                    trust = excluded.trust,
                    familiarity = excluded.familiarity,
                    relationship_summary = excluded.relationship_summary,
                    source_observation_id = excluded.source_observation_id,
                    updated_at = excluded.updated_at,
                    version = excluded.version
                """,
                (
                    str(stored.actor_id),
                    stored.actor_label,
                    stored.affinity,
                    stored.trust,
                    stored.familiarity,
                    stored.relationship_summary,
                    (
                        str(stored.source_observation_id)
                        if stored.source_observation_id is not None
                        else None
                    ),
                    stored.created_at.isoformat() if stored.created_at else None,
                    stored.updated_at.isoformat() if stored.updated_at else None,
                    stored.version,
                ),
            )
        return stored


def _row_to_record(row: sqlite3.Row) -> RelationshipSnapshotRecord:
    source = row["source_observation_id"]
    return RelationshipSnapshotRecord(
        actor_id=ActorId(str(row["actor_id"])),
        actor_label=row["actor_label"],
        affinity=float(row["affinity"]),
        trust=float(row["trust"]),
        familiarity=float(row["familiarity"]),
        relationship_summary=row["relationship_summary"],
        source_observation_id=ObservationId(str(source)) if source is not None else None,
        created_at=parse_datetime(str(row["created_at"])),
        updated_at=parse_datetime(str(row["updated_at"])),
        version=int(row["version"]),
    )
