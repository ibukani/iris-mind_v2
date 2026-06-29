"""Affect baseline のインメモリストア。"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.contracts.affect import AffectBaselineRecord, AffectStore
from iris.core.datetime_utils import now_utc

if TYPE_CHECKING:
    from datetime import datetime

    from iris.core.ids import ActorId


class InMemoryAffectStore(AffectStore):
    """Global / actor-scoped affect baseline のプロセス内ストア。"""

    def __init__(self) -> None:
        """空の affect store を初期化する。"""
        self._global: AffectBaselineRecord | None = None
        self._actor_records: dict[ActorId, AffectBaselineRecord] = {}

    @override
    async def get_global(self) -> AffectBaselineRecord | None:
        """Global affect baseline を返す。

        Returns:
            保存済み global baseline。存在しない場合は None。
        """
        return self._global

    @override
    async def upsert_global(self, record: AffectBaselineRecord) -> AffectBaselineRecord:
        """Global affect baseline を保存して返す。

        Returns:
            保存後の AffectBaselineRecord。

        Raises:
            ValueError: record.scope が global ではない場合。
        """
        if record.scope != "global":
            msg = "upsert_global requires scope='global'"
            raise ValueError(msg)
        now = now_utc()
        stored = _with_timestamps(
            record,
            created_at=self._global.created_at if self._global else record.created_at or now,
            updated_at=now,
        )
        self._global = stored
        return stored

    @override
    async def get_for_actor(self, actor_id: ActorId) -> AffectBaselineRecord | None:
        """Actor-scoped affect baseline を返す。

        Returns:
            保存済み actor baseline。存在しない場合は None。
        """
        return self._actor_records.get(actor_id)

    @override
    async def upsert_for_actor(self, record: AffectBaselineRecord) -> AffectBaselineRecord:
        """Actor-scoped affect baseline を保存して返す。

        Returns:
            保存後の AffectBaselineRecord。

        Raises:
            ValueError: record が actor scope と actor_id を満たさない場合。
        """
        if record.scope != "actor" or record.actor_id is None:
            msg = "upsert_for_actor requires scope='actor' and actor_id"
            raise ValueError(msg)
        now = now_utc()
        current = self._actor_records.get(record.actor_id)
        stored = _with_timestamps(
            record,
            created_at=current.created_at if current else record.created_at or now,
            updated_at=now,
        )
        self._actor_records[record.actor_id] = stored
        return stored


def _with_timestamps(
    record: AffectBaselineRecord,
    *,
    created_at: datetime | None,
    updated_at: datetime,
) -> AffectBaselineRecord:
    """Affect recordを時刻付きで再検証する。

    Returns:
        再構築したrecord。
    """
    return AffectBaselineRecord(
        scope=record.scope,
        actor_id=record.actor_id,
        mood_label=record.mood_label,
        valence=record.valence,
        arousal=record.arousal,
        dominance=record.dominance,
        affect_summary=record.affect_summary,
        source_observation_id=record.source_observation_id,
        created_at=created_at,
        updated_at=updated_at,
        version=record.version,
    )
