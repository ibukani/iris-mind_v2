"""SQLite-backed persistent MemoryStore implementation."""

from __future__ import annotations

import contextlib
import dataclasses
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING, override

from iris.adapters.memory.ports import MutableMemoryStore
from iris.contracts.memory import (
    MemoryId,
    MemoryKind,
    MemoryQuery,
    MemoryRecord,
    MemorySearchResult,
)
from iris.core.ids import ActorId, ObservationId, SpaceId

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence


class SQLiteMemoryStore(MutableMemoryStore):
    """SQLite-backed persistent MemoryStore.

    単一プロセス/ローカル利用前提。同期 sqlite3 I/O を直接実行する。
    高並行負荷でイベントループをブロックする懸念が出た場合は
    aiosqlite または asyncio.to_thread への移行を検討する。
    """

    def __init__(self, db_path: str | Path) -> None:
        """Initialize the store and create tables if missing."""
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create the memories table, filter indexes, and FTS5 virtual table if missing."""
        with self._transaction() as conn:
            conn.execute(
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
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_actor_id ON memories(actor_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_space_id ON memories(space_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_archived ON memories(archived);")
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts5 USING fts5(
                    text,
                    memory_id UNINDEXED
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        """Get a configured sqlite3 connection.

        Returns:
            sqlite3.Connection: A new configured connection.
        """
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @contextlib.contextmanager
    def _transaction(self) -> Generator[sqlite3.Connection]:
        """Provide a transactional sqlite connection that closes when done.

        Yields:
            sqlite3.Connection: An open, managed connection.
        """
        with contextlib.closing(self._connect()) as conn, conn:
            yield conn

    def search_fts5(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        """FTS5 全文検索でメモリレコードを返す。

        BM25 ランク付き。actor_id / space_id / kind / archived
        フィルタは post-filter 。

        Args:
            query: 検索クエリ。

        Returns:
            Sequence[MemorySearchResult]: スコア降順の検索結果。
        """
        if query.limit <= 0:
            return ()

        with self._transaction() as conn:
            cursor = conn.execute(
                """
                SELECT memory_id, rank
                FROM memories_fts5
                WHERE memories_fts5 MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query.text, query.limit * 4),
            )
            raw_rows = cursor.fetchall()

        results: list[MemorySearchResult] = []
        for row in raw_rows:
            record = self.get(MemoryId(row["memory_id"]))
            if record is None or not _matches_query(record, query):
                continue
            score = -float(row["rank"])
            results.append(MemorySearchResult(record=record, score=score))
            if len(results) >= query.limit:
                break
        return tuple(results)

    def _sync_fts5(
        self,
        memory_id: MemoryId,
        text: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """FTS5 インデックスを単一レコードで同期する。

        Args:
            memory_id: 同期対象のメモリ ID。
            text: インデックス対象テキスト。
            conn: 既存の接続。省略時は新しいトランザクションを開く。
        """
        if conn is not None:
            conn.execute(
                "DELETE FROM memories_fts5 WHERE memory_id = ?",
                (str(memory_id),),
            )
            conn.execute(
                "INSERT INTO memories_fts5(text, memory_id) VALUES(?, ?)",
                (text, str(memory_id)),
            )
            return
        with self._transaction() as c:
            c.execute(
                "DELETE FROM memories_fts5 WHERE memory_id = ?",
                (str(memory_id),),
            )
            c.execute(
                "INSERT INTO memories_fts5(text, memory_id) VALUES(?, ?)",
                (text, str(memory_id)),
            )

    @override
    def put(self, record: MemoryRecord) -> None:
        """Insert a new memory record with normalized timestamps.

        ``created_at`` が未指定なら現在の UTC を設定し、``updated_at`` が
        未指定なら ``created_at`` と同じ値を補う。
        """
        normalized = _normalize_for_put(record)
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    memory_id, text, actor_id, space_id, salience, kind,
                    confidence, source_observation_id, created_at, updated_at,
                    archived, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _record_to_row(normalized),
            )
            self._sync_fts5(record.id, record.text, conn=conn)

    @override
    def get(self, memory_id: MemoryId) -> MemoryRecord | None:
        """Return the record with the given id, or None."""
        with self._transaction() as conn:
            cursor = conn.execute(
                "SELECT * FROM memories WHERE memory_id = ?",
                (str(memory_id),),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return _row_to_record(row)

    @override
    def update(self, record: MemoryRecord) -> MemoryRecord:
        """Upsert a record with timestamp normalization.

        ``created_at`` 未指定時は、既存レコードがあればその ``created_at`` を
        引き継ぎ、なければ現在の UTC を設定する。``updated_at`` 未指定時は
        現在の UTC を設定する。

        Returns:
            MemoryRecord: 永続化された正規化済みレコード。
        """
        normalized = _normalize_for_update(self, record)
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    memory_id, text, actor_id, space_id, salience, kind,
                    confidence, source_observation_id, created_at, updated_at,
                    archived, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(memory_id) DO UPDATE SET
                    text=excluded.text,
                    actor_id=excluded.actor_id,
                    space_id=excluded.space_id,
                    salience=excluded.salience,
                    kind=excluded.kind,
                    confidence=excluded.confidence,
                    source_observation_id=excluded.source_observation_id,
                    updated_at=excluded.updated_at,
                    archived=excluded.archived,
                    metadata_json=excluded.metadata_json
                """,
                _record_to_row(normalized),
            )
            self._sync_fts5(record.id, record.text, conn=conn)
        return self.get(record.id) or record

    @override
    def archive(self, memory_id: MemoryId, *, archived: bool = True) -> MemoryRecord | None:
        """Toggle the archived flag for the given id and return the updated record.

        ``updated_at`` を現在の UTC に進める。

        Returns:
            MemoryRecord | None: 更新後レコード。存在しない ID の場合は None。
        """
        now_iso = datetime.now(tz=UTC).isoformat()
        with self._transaction() as conn:
            cursor = conn.execute(
                "SELECT memory_id FROM memories WHERE memory_id = ?",
                (str(memory_id),),
            )
            if cursor.fetchone() is None:
                return None
            conn.execute(
                "UPDATE memories SET archived = ?, updated_at = ? WHERE memory_id = ?",
                (1 if archived else 0, now_iso, str(memory_id)),
            )
            cursor = conn.execute(
                "SELECT text FROM memories WHERE memory_id = ?",
                (str(memory_id),),
            )
            text_row = cursor.fetchone()
            if text_row is not None:
                self._sync_fts5(memory_id, text_row["text"], conn=conn)
            cursor = conn.execute(
                "SELECT * FROM memories WHERE memory_id = ?",
                (str(memory_id),),
            )
            updated_row = cursor.fetchone()
            if not updated_row:
                return None
            return _row_to_record(updated_row)

    @override
    def filter(self, query: MemoryQuery) -> Sequence[MemoryRecord]:
        """Return records that match the given query filters."""
        clauses: list[str] = []
        params: list[object] = []
        if query.actor_id is not None:
            clauses.append("actor_id = ?")
            params.append(str(query.actor_id))
        if query.space_id is not None:
            clauses.append("space_id = ?")
            params.append(str(query.space_id))
        if query.kind is not None:
            clauses.append("kind = ?")
            params.append(str(query.kind))
        if not query.include_archived:
            clauses.append("archived = 0")

        sql = "SELECT * FROM memories"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)

        with self._transaction() as conn:
            cursor = conn.execute(sql, tuple(params))
            return tuple(_row_to_record(row) for row in cursor.fetchall())

    @override
    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        """Return text-matched results ranked by token overlap.

        永続化ストアではベクター類似度は使わず、決定論的な
        トークン重複カウントでランク付けする。

        Returns:
            Sequence[MemorySearchResult]: スコア降順の検索結果。
        """
        if query.limit <= 0:
            return ()

        eligible = self.filter(query)
        terms = tuple(term.casefold() for term in query.text.split() if term.strip())
        ranked: list[tuple[int, int, MemorySearchResult]] = []
        for index, record in enumerate(eligible):
            score = _score_record(record, terms)
            if score <= 0:
                continue
            ranked.append((score, index, MemorySearchResult(record=record, score=float(score))))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return tuple(result for _, _, result in ranked[: query.limit])


def _now_utc() -> datetime:
    """現在の timezone-aware UTC datetime を返す。

    Returns:
        datetime: timezone-aware な UTC タイムスタンプ。
    """
    return datetime.now(tz=UTC)


def _normalize_for_put(record: MemoryRecord) -> MemoryRecord:
    """``put`` 用のタイムスタンプ正規化レコードを返す。

    ``created_at`` 未指定なら現在の UTC を、``updated_at`` 未指定なら
    ``created_at`` (補完後の値) と同じものを設定する。

    Args:
        record: 元のメモリレコード。

    Returns:
        MemoryRecord: タイムスタンプを補完した新しいメモリレコード。
    """
    if record.created_at is None and record.updated_at is None:
        now = _now_utc()
        return dataclasses.replace(record, created_at=now, updated_at=now)
    if record.created_at is None:
        created = record.updated_at
        if created is None:  # pragma: no cover -- defensive
            created = _now_utc()
        return dataclasses.replace(record, created_at=created)
    if record.updated_at is None:
        return dataclasses.replace(record, updated_at=record.created_at)
    return record


def _normalize_for_update(
    store: SQLiteMemoryStore,
    record: MemoryRecord,
) -> MemoryRecord:
    """``update`` 用のタイムスタンプ正規化レコードを返す。

    ``record.created_at`` が None の場合、既存レコードがあればその
    ``created_at`` を引き継ぎ、なければ現在の UTC を設定する。
    ``updated_at`` 未指定時は現在の UTC を設定する。新規作成経路で
    両方を補完する場合は同一の now 値を使う。

    Args:
        store: 既存レコード参照に使うストア。
        record: 元のメモリレコード。

    Returns:
        MemoryRecord: タイムスタンプを補完した新しいメモリレコード。
    """
    existing = store.get(record.id)
    existing_created = existing.created_at if existing is not None else None

    if record.created_at is None and record.updated_at is None:
        if existing_created is not None:
            return dataclasses.replace(
                record,
                created_at=existing_created,
                updated_at=_now_utc(),
            )
        now = _now_utc()
        return dataclasses.replace(record, created_at=now, updated_at=now)

    if record.created_at is None:
        if existing_created is not None:
            record = dataclasses.replace(record, created_at=existing_created)
        else:
            record = dataclasses.replace(record, created_at=_now_utc())

    if record.updated_at is None:
        record = dataclasses.replace(record, updated_at=_now_utc())

    return record


def _record_to_row(record: MemoryRecord) -> tuple[object, ...]:
    return (
        str(record.id),
        record.text,
        str(record.actor_id) if record.actor_id is not None else None,
        str(record.space_id) if record.space_id is not None else None,
        float(record.salience),
        str(record.kind),
        float(record.confidence),
        str(record.source_observation_id) if record.source_observation_id is not None else None,
        _isoformat(record.created_at),
        _isoformat(record.updated_at),
        1 if record.archived else 0,
        json.dumps(dict(record.metadata)),
    )


def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
    actor_id_value = row["actor_id"]
    space_id_value = row["space_id"]
    source_observation_id_value = row["source_observation_id"]
    metadata_raw = row["metadata_json"]
    return MemoryRecord(
        id=MemoryId(row["memory_id"]),
        text=row["text"],
        actor_id=ActorId(actor_id_value) if actor_id_value else None,
        space_id=SpaceId(space_id_value) if space_id_value else None,
        salience=float(row["salience"]),
        kind=MemoryKind(row["kind"]),
        confidence=float(row["confidence"]),
        source_observation_id=(
            ObservationId(source_observation_id_value) if source_observation_id_value else None
        ),
        created_at=_parse_datetime(row["created_at"]),
        updated_at=_parse_datetime(row["updated_at"]),
        archived=bool(row["archived"]),
        metadata=json.loads(metadata_raw) if metadata_raw else {},
    )


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None

    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _matches_query(record: MemoryRecord, query: MemoryQuery) -> bool:
    """レコードが MemoryQuery のフィルタ条件に一致するか判定する。

    Args:
        record: 判定対象のメモリレコード。
        query: フィルタ条件を含むクエリ。

    Returns:
        bool: すべての条件を満たす場合は True 。
    """
    return (
        (query.include_archived or not record.archived)
        and (query.actor_id is None or record.actor_id == query.actor_id)
        and (query.space_id is None or record.space_id == query.space_id)
        and (query.kind is None or record.kind == query.kind)
    )


def _score_record(record: MemoryRecord, terms: tuple[str, ...]) -> int:
    if not terms:
        return 0
    text = record.text.casefold()
    return sum(1 for term in terms if term in text)
