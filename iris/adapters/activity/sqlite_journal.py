"""SQLite-backed durable ActivityJournal実装。"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import threading
from typing import TYPE_CHECKING, ClassVar, override

from iris.runtime.state.activity_journal import (
    ActivityAppendResult,
    ActivityAppendSkipReason,
    ActivityJournal,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from iris.contracts.activity import ActivityEventRecord

type MetadataMapping = dict[str, str]
type JsonStorageMapping = dict[str, str]


@dataclass(frozen=True)
class _EventPayload:
    """SQLiteへ格納するlossless JSON payload。"""

    observation_id: str | None
    provider_event_id: str | None
    provider_sequence: int | None
    actor_id: str | None
    account_id: str | None
    device_id: str | None
    space_id: str | None
    source: str | None
    kind: str
    occurred_at: str
    received_at: str
    metadata: MetadataMapping


class SQLiteActivityJournal(ActivityJournal):
    """SQLite-backed durable ActivityJournal。

    Append-only audit logとして``state.backend = "sqlite"``選択時に利用される。
    Provider event dedupeは永続化され、新しいstore instanceへ引き継がれる。
    """

    _write_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, db_path: str | Path) -> None:
        """データベースパスでjournalを初期化する。

        Args:
            db_path: SQLiteデータベースファイルへのパス。
        """
        self._db_path = Path(db_path)
        self._conn_lock = threading.RLock()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = self._connect()
        self._init_db()

    def _init_db(self) -> None:
        """activity_events tableと必要indexを初期化する。"""
        schema = """
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
        );
        """
        dedupe_index = """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_events_provider_event
        ON activity_events(source, provider_event_id)
        WHERE source IS NOT NULL AND provider_event_id IS NOT NULL;
        """
        occurred_index = """
        CREATE INDEX IF NOT EXISTS idx_activity_events_occurred_at
        ON activity_events(occurred_at);
        """
        with self._transaction() as conn:
            conn.execute(schema)
            conn.execute(dedupe_index)
            conn.execute(occurred_index)

    def _connect(self) -> sqlite3.Connection:
        """設定済みsqlite3 connectionを取得する。

        Returns:
            sqlite3.Connection: 設定済みのconnection。
        """
        conn = sqlite3.connect(self._db_path, timeout=5.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        return conn

    @contextlib.contextmanager
    def _transaction(self) -> Generator[sqlite3.Connection]:
        """Transactional sqlite connectionを供給するcontext manager。

        Yields:
            sqlite3.Connection: 開いた管理対象connection。
        """
        with self._conn_lock, self._conn:
            yield self._conn

    def close(self) -> None:
        """永続connectionを閉じる。"""
        with self._conn_lock:
            self._conn.close()

    def __del__(self) -> None:
        """未closeのconnectionを解放する。"""
        if hasattr(self, "_conn"):
            self.close()

    @contextlib.contextmanager
    def _immediate_transaction(self) -> Generator[sqlite3.Connection]:
        """書き込み直列化用の ``BEGIN IMMEDIATE`` transaction context manager。

        SQLiteの既定 ``BEGIN DEFERRED`` は最初の書き込みまでwriter同士が
        共有ロックを取らず、SELECT通過直後に他writerがINSERTする
        TOCTOU窓が開く。``IMMEDIATE`` で開始時にRESERVEDロックを獲得し、
        SELECTとINSERTを単一writerに直列化することで窓を潰す。

        ``BEGIN IMMEDIATE`` 自体が ``OperationalError: database is locked``
        等で失敗した場合、後続の ``ROLLBACK`` が
        ``cannot rollback - no transaction is active`` で
        元例外をマスクしないよう、トランザクション開始成功時のみ
        ``ROLLBACK`` を試行する。``ROLLBACK`` 自体が失敗しても
        元例外の伝搬を妨げてはならない。

        Yields:
            sqlite3.Connection: ``BEGIN IMMEDIATE`` を開始した管理対象connection。
        """
        txn_active = False
        with self._conn_lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                txn_active = True
                yield self._conn
                self._conn.commit()
            except Exception:
                if txn_active:
                    with contextlib.suppress(sqlite3.OperationalError):
                        self._conn.execute("ROLLBACK")
                raise

    @override
    async def append(self, event: ActivityEventRecord) -> ActivityAppendResult:
        """eventをjournalへ追加する。既存IDは更新せず、provider event重複は拒否する。

        Args:
            event: 追加対象のactivity event。

        Returns:
            ActivityAppendResult: 受理結果。
        """
        return await asyncio.to_thread(self._append_sync, event)

    def _append_sync(self, event: ActivityEventRecord) -> ActivityAppendResult:
        provider_key = _provider_key(event)
        payload = _serialize_event(event)
        try:
            self._insert_immediate_sync(event, payload, provider_key)
        except sqlite3.IntegrityError as exc:
            # BEGIN IMMEDIATE で他writerを直列化しているため通常は上の
            # in-transaction SELECTで弾けるが、稀な競合への最終フォールバック。
            # PK違反(activity_id) と unique partial index 違反(provider_event_id)
            # をエラーメッセージで判別し、Protocol契約に従い ActivityAppendResult
            # へ変換する(例外を漏らさない)。
            reason = _classify_integrity_error(exc)
            return ActivityAppendResult(accepted=False, event=None, reason=reason)
        except sqlite3.OperationalError:
            # BEGIN IMMEDIATE 失敗(database is locked 等)で
            # busy_timeout を超過した場合など。Protocol契約上 append は
            # 例外を漏らさないため BACKEND_UNAVAILABLE へ変換する。
            return ActivityAppendResult(
                accepted=False,
                event=None,
                reason=ActivityAppendSkipReason.BACKEND_UNAVAILABLE,
            )
        return ActivityAppendResult(accepted=True, event=event)

    def _insert_immediate_sync(
        self,
        event: ActivityEventRecord,
        payload: _EventPayload,
        provider_key: tuple[str, str] | None,
    ) -> None:
        """``BEGIN IMMEDIATE`` 内で dedupe 検査とINSERTを原子的に実行する。

        activity_id PK と ``(source, provider_event_id)`` unique partial index の
        両方をin-transaction SELECTで先に確認し、問題なければ1件のINSERTを行う。
        競合制約違反時は ``sqlite3.IntegrityError`` をそのまま呼び出し側へ
        送出する(分類は呼び出し側 ``_append_sync`` で行う)。

        Raises:
            sqlite3.IntegrityError: activity_id または provider_event_id 重複時。
        """
        with self._write_lock, self._immediate_transaction() as conn:
            existing_cursor: sqlite3.Cursor = conn.execute(
                "SELECT 1 FROM activity_events WHERE activity_id = ?",
                (str(event.activity_id),),
            )
            existing_row: sqlite3.Row | None = existing_cursor.fetchone()
            if existing_row is not None:
                message = "duplicate activity_id"
                raise sqlite3.IntegrityError(message)
            if provider_key is not None:
                duplicate_cursor: sqlite3.Cursor = conn.execute(
                    """
                    SELECT 1 FROM activity_events
                    WHERE source = ? AND provider_event_id = ?
                    """,
                    (provider_key[0], provider_key[1]),
                )
                duplicate_row: sqlite3.Row | None = duplicate_cursor.fetchone()
                if duplicate_row is not None:
                    message = "duplicate provider_event_id"
                    raise sqlite3.IntegrityError(message)
            conn.execute(
                """
                INSERT INTO activity_events (
                    activity_id, source, provider_event_id, actor_id, space_id,
                    activity_kind, occurred_at, received_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.activity_id),
                    payload.source,
                    payload.provider_event_id,
                    payload.actor_id,
                    payload.space_id,
                    payload.kind,
                    payload.occurred_at,
                    payload.received_at,
                    json.dumps(_payload_to_json_dict(payload)),
                ),
            )


def _provider_key(event: ActivityEventRecord) -> tuple[str, str] | None:
    """Provider dedupe用keyを返す。source/provider_event_idが揃う場合のみ返す。

    Args:
        event: 対象event。

    Returns:
        tuple[str, str] | None: provider dedupe key。揃わなければNone。
    """
    if event.source is None or event.provider_event_id is None:
        return None
    return (event.source, event.provider_event_id)


def _classify_integrity_error(exc: sqlite3.IntegrityError) -> ActivityAppendSkipReason:
    """``sqlite3.IntegrityError`` をProtocol契約上の skip reason へ分類する。

    メッセージに ``provider_event_id`` が含まれていれば unique partial index 違反
    (DUPLICATE_PROVIDER_EVENT) 、 ``activity_id`` のみなら PK 違反
    (DUPLICATE_ACTIVITY_ID) とみなす。判別不能時は保守側として
    DUPLICATE_PROVIDER_EVENT を返す。

    Args:
        exc: SQLite から送出された IntegrityError。

    Returns:
        ActivityAppendSkipReason: 該当 skip reason。
    """
    message = str(exc)
    if "activity_id" in message and "provider_event_id" not in message:
        return ActivityAppendSkipReason.DUPLICATE_ACTIVITY_ID
    if "provider_event_id" in message and "activity_id" not in message:
        return ActivityAppendSkipReason.DUPLICATE_PROVIDER_EVENT
    # 判別不能時は raw error メッセージで PK違反と unique partial index 違反の
    # どちらかに識別する。SQLite の標準メッセージには対象列名が含まれる。
    lowered = message.lower()
    if "activity_events.activity_id" in lowered:
        return ActivityAppendSkipReason.DUPLICATE_ACTIVITY_ID
    return ActivityAppendSkipReason.DUPLICATE_PROVIDER_EVENT


def _serialize_event(event: ActivityEventRecord) -> _EventPayload:
    """ActivityEventRecordをlossless JSON payloadへ変換する。

    Args:
        event: 変換元event。

    Returns:
        _EventPayload: lossless payload。
    """
    metadata: MetadataMapping = {str(k): str(v) for k, v in event.metadata.items()}
    return _EventPayload(
        observation_id=str(event.observation_id) if event.observation_id else None,
        provider_event_id=event.provider_event_id,
        provider_sequence=event.provider_sequence,
        actor_id=str(event.actor_id) if event.actor_id else None,
        account_id=str(event.account_id) if event.account_id else None,
        device_id=str(event.device_id) if event.device_id else None,
        space_id=str(event.space_id) if event.space_id else None,
        source=event.source,
        kind=event.kind.value,
        occurred_at=event.occurred_at.isoformat(),
        received_at=event.received_at.isoformat(),
        metadata=metadata,
    )


def _payload_to_json_dict(payload: _EventPayload) -> JsonStorageMapping:
    """payloadをJSON互換dictへ変換する。Noneは空文字として格納する。

    Args:
        payload: 変換元payload。

    Returns:
        JsonStorageMapping: JSON互換dict。
    """
    return {
        "observation_id": payload.observation_id or "",
        "provider_event_id": payload.provider_event_id or "",
        "provider_sequence": (
            str(payload.provider_sequence) if payload.provider_sequence is not None else ""
        ),
        "actor_id": payload.actor_id or "",
        "account_id": payload.account_id or "",
        "device_id": payload.device_id or "",
        "space_id": payload.space_id or "",
        "source": payload.source or "",
        "kind": payload.kind,
        "occurred_at": payload.occurred_at,
        "received_at": payload.received_at,
        "metadata": json.dumps(payload.metadata),
    }
