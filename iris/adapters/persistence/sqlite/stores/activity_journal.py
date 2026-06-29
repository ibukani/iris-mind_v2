"""SQLite-backed durable ActivityJournal実装."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import TYPE_CHECKING, override

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.future import select

from iris.adapters.persistence.sqlite.context import (
    SQLiteDatabaseInput,
    resolve_database_manager,
)
from iris.adapters.persistence.sqlite.schema.activity import ActivityEventModel
from iris.runtime.state.activity_journal import (
    ActivityAppendResult,
    ActivityAppendSkipReason,
    ActivityJournal,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

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

    def __init__(self, db: SQLiteDatabaseInput) -> None:
        """データベースパスでjournalを初期化する。

        Args:
            db: SQLiteデータベースファイルへのパス、または永続化コンテキスト。
        """
        self._db = resolve_database_manager(db)

    async def close(self) -> None:
        """永続connectionを閉じる。"""
        await self._db.close()

    @override
    async def append(self, event: ActivityEventRecord) -> ActivityAppendResult:
        """eventをjournalへ追加する。既存IDは更新せず、provider event重複は拒否する。

        Args:
            event: 追加対象のactivity event。

        Returns:
            ActivityAppendResult: 受理結果。
        """
        provider_key = _provider_key(event)
        payload = _serialize_event(event)

        try:
            async with self._db.transaction() as session:
                return await self._insert_sync(session, event, payload, provider_key)
        except IntegrityError as exc:
            reason = _classify_integrity_error(exc)
            return ActivityAppendResult(accepted=False, event=None, reason=reason)
        except OperationalError:
            return ActivityAppendResult(
                accepted=False,
                event=None,
                reason=ActivityAppendSkipReason.BACKEND_UNAVAILABLE,
            )

    @staticmethod
    async def _insert_sync(
        session: AsyncSession,
        event: ActivityEventRecord,
        payload: _EventPayload,
        provider_key: tuple[str, str] | None,
    ) -> ActivityAppendResult:
        """session内で dedupe 検査とINSERTを実行する。

        activity_id PK と ``(source, provider_event_id)`` unique partial index の
        両方をin-transaction SELECTで先に確認し、問題なければ1件のINSERTを行う。

        Returns:
            ActivityAppendResult: 結果

        Raises:
            IntegrityError: activity_id または provider_event_id 重複時。
        """
        existing = await session.scalar(
            select(ActivityEventModel).where(
                ActivityEventModel.activity_id == str(event.activity_id)
            )
        )
        if existing is not None:
            msg = "duplicate activity_id"
            raise IntegrityError(msg, params=None, orig=Exception("activity_id"))

        if provider_key is not None:
            duplicate = await session.scalar(
                select(ActivityEventModel).where(
                    ActivityEventModel.source == provider_key[0],
                    ActivityEventModel.provider_event_id == provider_key[1],
                )
            )
            if duplicate is not None:
                msg = "duplicate provider_event_id"
                raise IntegrityError(msg, params=None, orig=Exception("provider_event_id"))

        model = ActivityEventModel(
            activity_id=str(event.activity_id),
            source=payload.source,
            provider_event_id=payload.provider_event_id,
            actor_id=payload.actor_id,
            space_id=payload.space_id,
            activity_kind=payload.kind,
            occurred_at=payload.occurred_at,
            received_at=payload.received_at,
            payload_json=json.dumps(_payload_to_json_dict(payload)),
        )
        session.add(model)
        return ActivityAppendResult(accepted=True, event=event)


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


def _classify_integrity_error(exc: IntegrityError) -> ActivityAppendSkipReason:
    """``IntegrityError`` をProtocol契約上の skip reason へ分類する。

    メッセージに ``provider_event_id`` が含まれていれば unique partial index 違反
    (DUPLICATE_PROVIDER_EVENT) 、 ``activity_id`` のみなら PK 違反
    (DUPLICATE_ACTIVITY_ID) とみなす。判別不能時は保守側として
    DUPLICATE_PROVIDER_EVENT を返す。

    Args:
        exc: SQLAlchemy から送出された IntegrityError。

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
