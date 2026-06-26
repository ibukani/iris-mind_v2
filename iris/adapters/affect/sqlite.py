"""SQLite-backed affect baseline store。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3
from typing import override

from iris.contracts.affect import AffectBaselineRecord, AffectScope, AffectStore
from iris.core.datetime_utils import now_utc, parse_datetime
from iris.core.ids import ActorId, ObservationId

_GLOBAL_KEY = "__global__"


class SQLiteAffectStore(AffectStore):
    """Global / actor-scoped affect baseline の SQLite store。"""

    def __init__(self, db_path: str | Path) -> None:
        """SQLite DB path を受け取り、必要な table を作成する。"""
        self._db_path = Path(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """実用的な pragma を設定した SQLite connection を返す。

        Returns:
            初期 pragma を設定した sqlite3.Connection。
        """
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self) -> None:
        """affect_baselines table を作成する。"""
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS affect_baselines (
                    scope TEXT NOT NULL,
                    owner_key TEXT PRIMARY KEY,
                    actor_id TEXT,
                    mood_label TEXT,
                    valence REAL NOT NULL,
                    arousal REAL NOT NULL,
                    dominance REAL NOT NULL,
                    affect_summary TEXT,
                    source_observation_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    CHECK (
                        (scope = 'global' AND actor_id IS NULL AND owner_key = '__global__')
                        OR
                        (scope = 'actor' AND actor_id IS NOT NULL AND owner_key = actor_id)
                    )
                )
                """,
            )

    @override
    def get_global(self) -> AffectBaselineRecord | None:
        """Global affect baseline を取得する。

        Returns:
            保存済み global baseline。存在しない場合は None。
        """
        return self._get(_GLOBAL_KEY)

    @override
    def upsert_global(self, record: AffectBaselineRecord) -> AffectBaselineRecord:
        """Global affect baseline を upsert して保存後の値を返す。

        Returns:
            保存後の AffectBaselineRecord。

        Raises:
            ValueError: record.scope が global ではない場合。
        """
        if record.scope != "global":
            msg = "upsert_global requires scope='global'"
            raise ValueError(msg)
        return self._upsert(record, owner_key=_GLOBAL_KEY)

    @override
    def get_for_actor(self, actor_id: ActorId) -> AffectBaselineRecord | None:
        """Actor-scoped affect baseline を取得する。

        Returns:
            保存済み actor baseline。存在しない場合は None。
        """
        return self._get(str(actor_id))

    @override
    def upsert_for_actor(self, record: AffectBaselineRecord) -> AffectBaselineRecord:
        """Actor-scoped affect baseline を upsert して保存後の値を返す。

        Returns:
            保存後の AffectBaselineRecord。

        Raises:
            ValueError: record が actor scope と actor_id を満たさない場合。
        """
        if record.scope != "actor" or record.actor_id is None:
            msg = "upsert_for_actor requires scope='actor' and actor_id"
            raise ValueError(msg)
        return self._upsert(record, owner_key=str(record.actor_id))

    def _get(self, owner_key: str) -> AffectBaselineRecord | None:
        """Owner key に対応する affect baseline を取得する。

        Returns:
            保存済み AffectBaselineRecord。存在しない場合は None。
        """
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT scope, actor_id, mood_label, valence, arousal, dominance,
                       affect_summary, source_observation_id,
                       created_at, updated_at, version
                FROM affect_baselines
                WHERE owner_key = ?
                """,
                (owner_key,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    def _upsert(self, record: AffectBaselineRecord, *, owner_key: str) -> AffectBaselineRecord:
        """Affect baseline を upsert して保存後の値を返す。

        Returns:
            保存後の AffectBaselineRecord。
        """
        now = now_utc()
        current = self._get(owner_key)
        stored = replace(
            record,
            created_at=current.created_at if current else record.created_at or now,
            updated_at=now,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO affect_baselines (
                    scope, owner_key, actor_id, mood_label, valence, arousal, dominance,
                    affect_summary, source_observation_id, created_at, updated_at, version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_key) DO UPDATE SET
                    mood_label = excluded.mood_label,
                    valence = excluded.valence,
                    arousal = excluded.arousal,
                    dominance = excluded.dominance,
                    affect_summary = excluded.affect_summary,
                    source_observation_id = excluded.source_observation_id,
                    updated_at = excluded.updated_at,
                    version = excluded.version
                """,
                (
                    stored.scope,
                    owner_key,
                    str(stored.actor_id) if stored.actor_id is not None else None,
                    stored.mood_label,
                    stored.valence,
                    stored.arousal,
                    stored.dominance,
                    stored.affect_summary,
                    str(stored.source_observation_id)
                    if stored.source_observation_id is not None
                    else None,
                    stored.created_at.isoformat() if stored.created_at else None,
                    stored.updated_at.isoformat() if stored.updated_at else None,
                    stored.version,
                ),
            )
        return stored


def _row_to_record(row: sqlite3.Row) -> AffectBaselineRecord:
    """SQLite row を AffectBaselineRecord に変換する。

    Returns:
        変換済み AffectBaselineRecord。
    """
    source = row["source_observation_id"]
    actor = row["actor_id"]
    return AffectBaselineRecord(
        scope=_scope_from_row(row["scope"]),
        actor_id=ActorId(str(actor)) if actor is not None else None,
        mood_label=row["mood_label"],
        valence=float(row["valence"]),
        arousal=float(row["arousal"]),
        dominance=float(row["dominance"]),
        affect_summary=row["affect_summary"],
        source_observation_id=ObservationId(str(source)) if source is not None else None,
        created_at=parse_datetime(row["created_at"]),
        updated_at=parse_datetime(row["updated_at"]),
        version=int(row["version"]),
    )


def _scope_from_row(value: object) -> AffectScope:
    """SQLite row の scope 値を AffectScope に検証変換する。

    Returns:
        検証済み AffectScope。

    Raises:
        ValueError: scope 値が未対応の場合。
    """
    scope = str(value)
    if scope == "global":
        return "global"
    if scope == "actor":
        return "actor"
    msg = f"unsupported affect scope: {scope}"
    raise ValueError(msg)
