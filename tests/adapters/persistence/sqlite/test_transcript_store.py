"""SQLiteTranscriptStore tests。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import ValidationError
import pytest

from iris.adapters.persistence.sqlite.stores.transcript import SQLiteTranscriptStore
from iris.contracts.transcript import (
    TranscriptAccessScope,
    TranscriptExportRequest,
    TranscriptPageRequest,
    TranscriptQuery,
    TranscriptRecord,
    TranscriptRole,
    TranscriptSource,
    TranscriptSubjectKind,
    TranscriptTimeRange,
)
from iris.core.ids import AccountId, ActorId, ObservationId, SessionId, SpaceId, TranscriptId
from iris.runtime.auth.errors import RuntimePermissionDeniedError
from iris.runtime.auth.principals import ClientKind, ClientPrincipal
from iris.runtime.auth.scopes import AuthScope
from iris.runtime.transcript import TranscriptReadService

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.anyio


def _record(
    transcript_id: str,
    content: str,
    *,
    actor_id: str = "actor-1",
    space_id: str = "space-1",
    occurred_at: datetime | None = None,
    retention_until: datetime | None = None,
) -> TranscriptRecord:
    now = occurred_at or datetime(2026, 7, 1, tzinfo=UTC)
    return TranscriptRecord(
        transcript_id=TranscriptId(transcript_id),
        subject_kind=TranscriptSubjectKind.ACTOR,
        subject_id=actor_id,
        role=TranscriptRole.USER,
        source=TranscriptSource.INLINE_RESPONSE,
        content=content,
        occurred_at=now,
        recorded_at=now,
        session_id=SessionId("session-1"),
        observation_id=ObservationId(f"obs-{transcript_id}"),
        actor_id=ActorId(actor_id),
        account_id=AccountId("account-1"),
        space_id=SpaceId(space_id),
        retention_until=retention_until,
        metadata={"kind": "test"},
    )


def _transcript_read_principal(*scopes: AuthScope) -> ClientPrincipal:
    return ClientPrincipal(
        client_id="transcript-reader",
        client_kind=ClientKind.ADMIN,
        provider=None,
        allowed_providers=frozenset(),
        scopes=frozenset(scopes),
        observation_capabilities=frozenset(),
        authenticated=True,
    )


async def _assert_read_service_behavior(store: SQLiteTranscriptStore) -> None:
    service = TranscriptReadService(store)
    principal = _transcript_read_principal(AuthScope.TRANSCRIPT_READ)
    scope = TranscriptAccessScope(
        actor_id=ActorId("actor-1"),
        space_id=SpaceId("space-1"),
    )
    first_at = datetime(2026, 7, 1, tzinfo=UTC)

    first_page = await service.query(
        principal,
        TranscriptPageRequest(
            scope=scope,
            time_range=TranscriptTimeRange(end=first_at + timedelta(seconds=2)),
            limit=1,
        ),
    )
    assert tuple(record.transcript_id for record in first_page.records) == (TranscriptId("tr-1"),)
    assert first_page.next_cursor is not None

    second_page = await service.query(
        principal,
        TranscriptPageRequest(scope=scope, limit=1, cursor=first_page.next_cursor),
    )
    assert tuple(record.transcript_id for record in second_page.records) == (TranscriptId("tr-4"),)
    assert second_page.next_cursor is None

    exported = await service.export(
        principal,
        TranscriptExportRequest(scope=scope, max_records=1),
    )
    assert tuple(record.transcript_id for record in exported.records) == (TranscriptId("tr-1"),)
    assert exported.truncated is True
    assert exported.next_cursor is not None

    with pytest.raises(RuntimePermissionDeniedError):
        await service.query(
            _transcript_read_principal(),
            TranscriptPageRequest(scope=scope),
        )
    with pytest.raises(ValidationError):
        TranscriptAccessScope()


async def test_sqlite_transcript_store_appends_and_queries_by_boundary(tmp_path: Path) -> None:
    """Actor/space境界で transcript を取得する。"""
    store = SQLiteTranscriptStore(tmp_path / "state.sqlite3")
    try:
        await store.append(
            (
                _record("tr-1", "first"),
                _record(
                    "tr-4",
                    "second",
                    occurred_at=datetime(2026, 7, 1, 0, 0, 1, tzinfo=UTC),
                ),
                _record("tr-2", "other-space", space_id="space-2"),
                _record("tr-3", "other-actor", actor_id="actor-2"),
            )
        )

        records = await store.query(
            TranscriptQuery(
                subject_kind=TranscriptSubjectKind.ACTOR,
                subject_id="actor-1",
                space_id=SpaceId("space-1"),
            )
        )

        assert tuple(record.content for record in records) == ("first", "second")
        after_cursor_records = await store.query(
            TranscriptQuery(
                actor_id=ActorId("actor-1"),
                space_id=SpaceId("space-1"),
                after_occurred_at=records[0].occurred_at,
                after_transcript_id=records[0].transcript_id,
            )
        )
        await _assert_read_service_behavior(store)
    finally:
        store.close()
    assert records[0].metadata["kind"] == "test"
    assert tuple(record.transcript_id for record in after_cursor_records) == (TranscriptId("tr-4"),)


async def test_sqlite_transcript_store_ignores_duplicate_transcript_id(tmp_path: Path) -> None:
    """同じ transcript_id の再挿入は先行 record を維持する。"""
    store = SQLiteTranscriptStore(tmp_path / "state.sqlite3")
    try:
        first = _record("tr-1", "first")
        duplicate = first.model_copy(update={"content": "changed on retry"})
        await store.append((first, duplicate))

        records = await store.query(TranscriptQuery(actor_id=ActorId("actor-1")))

        assert tuple(record.content for record in records) == ("first",)
    finally:
        store.close()


async def test_sqlite_transcript_store_prunes_expired_records(tmp_path: Path) -> None:
    """retention_until を過ぎた record だけを削除する。"""
    store = SQLiteTranscriptStore(tmp_path / "state.sqlite3")
    now = datetime(2026, 7, 1, tzinfo=UTC)
    try:
        await store.append(
            (
                _record("tr-old", "old", retention_until=now - timedelta(seconds=1)),
                _record("tr-new", "new", retention_until=now + timedelta(days=1)),
            )
        )

        result = await store.prune_expired(now)
        records = await store.query(TranscriptQuery(actor_id=ActorId("actor-1")))

        assert result.deleted_count == 1
        assert tuple(record.content for record in records) == ("new",)
    finally:
        store.close()


async def test_sqlite_transcript_store_applies_key_depth_limit(tmp_path: Path) -> None:
    """key単位の最大保持件数を超えた古い record を削除する。"""
    store = SQLiteTranscriptStore(tmp_path / "state.sqlite3", max_records_per_key=2)
    base = datetime(2026, 7, 1, tzinfo=UTC)
    try:
        await store.append(
            tuple(
                _record(
                    f"tr-{index}",
                    f"content-{index}",
                    occurred_at=base + timedelta(seconds=index),
                )
                for index in range(3)
            )
        )

        records = await store.query(
            TranscriptQuery(
                subject_kind=TranscriptSubjectKind.ACTOR,
                subject_id="actor-1",
                space_id=SpaceId("space-1"),
            )
        )

        assert tuple(record.content for record in records) == ("content-1", "content-2")
    finally:
        store.close()
