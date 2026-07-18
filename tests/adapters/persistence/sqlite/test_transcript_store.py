"""SQLiteTranscriptStore tests。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import ValidationError
import pytest

from iris.adapters.persistence.sqlite.stores.transcript import SQLiteTranscriptStore
from iris.contracts.ordering import OrderingConflictReason, OrderingDecisionKind
from iris.contracts.transcript import (
    TranscriptAccessScope,
    TranscriptCleanupExclusionReason,
    TranscriptCleanupRequest,
    TranscriptDeletionPolicy,
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
from iris.runtime.transcript import TranscriptCleanupService, TranscriptReadService

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


async def _assert_cleanup_dry_run(
    store: SQLiteTranscriptStore,
    scope: TranscriptAccessScope,
    cutoff: datetime,
) -> TranscriptCleanupRequest:
    """Cleanup dry-run、gate、legal hold、operation reuseを確認する。

    Returns:
        Execution phaseで再利用するcleanup request。
    """
    principal = _transcript_read_principal(AuthScope.TRANSCRIPT_CLEANUP)
    cleanup = TranscriptCleanupService(store, enabled=True)
    request = TranscriptCleanupRequest(
        operation_id="cleanup-dry-run",
        scope=scope,
        cutoff=cutoff,
    )
    deferred = await TranscriptCleanupService(store).cleanup(principal, request)
    assert deferred.decision.decision is OrderingDecisionKind.DEFER
    dry_run = await cleanup.cleanup(principal, request)
    assert dry_run.target_count == 2
    assert dry_run.eligible_count == 1
    assert dry_run.deleted_count == 0
    assert dry_run.excluded_count == 1
    assert dry_run.exclusions[0].reason is TranscriptCleanupExclusionReason.LEGAL_HOLD
    assert dry_run.decision.decision is OrderingDecisionKind.ACCEPT
    assert await cleanup.cleanup(principal, request) == dry_run.model_copy(
        update={"already_applied": True}
    )
    policy_result = await cleanup.cleanup(
        principal,
        request.model_copy(
            update={
                "operation_id": "cleanup-cross-store-policy",
                "policy": TranscriptDeletionPolicy(delete_canonical_memory=True),
            }
        ),
    )
    assert policy_result.eligible_count == 0
    assert policy_result.excluded_count == 2
    assert policy_result.exclusions[0].reason is TranscriptCleanupExclusionReason.POLICY_DISABLED
    return request


async def _assert_cleanup_execution(
    store: SQLiteTranscriptStore,
    db_path: Path,
    request: TranscriptCleanupRequest,
) -> None:
    """Cleanup execution、restart idempotency、operation conflictを確認する。"""
    principal = _transcript_read_principal(AuthScope.TRANSCRIPT_CLEANUP)
    cleanup = TranscriptCleanupService(store, enabled=True)
    execution_request = request.model_copy(
        update={"operation_id": "cleanup-execution", "dry_run": False}
    )
    execution = await cleanup.cleanup(principal, execution_request)
    assert execution.deleted_count == 1
    assert execution.excluded_count == 1
    remaining = await store.query(TranscriptQuery(actor_id=ActorId("actor-1")))
    assert tuple(record.content for record in remaining) == ("held",)
    assert (await cleanup.cleanup(principal, execution_request)).already_applied

    restarted_store = SQLiteTranscriptStore(db_path)
    try:
        restarted_cleanup = TranscriptCleanupService(restarted_store, enabled=True)
        durable_result = await restarted_cleanup.cleanup(principal, execution_request)
        assert durable_result.already_applied
    finally:
        restarted_store.close()

    conflict = await cleanup.cleanup(
        principal,
        execution_request.model_copy(update={"cutoff": request.cutoff + timedelta(seconds=1)}),
    )
    assert conflict.decision.decision is OrderingDecisionKind.REJECT_CONFLICT
    assert conflict.decision.conflict is not None
    assert conflict.decision.conflict.reason is OrderingConflictReason.VERSION_CONFLICT


async def _assert_prune_and_cleanup_flow(
    store: SQLiteTranscriptStore,
    db_path: Path,
    now: datetime,
) -> None:
    """Retention prune と scoped cleanup の連携を確認する。"""
    await store.append(
        (
            _record("tr-old", "old").model_copy(
                update={"retention_until": now - timedelta(seconds=1)}
            ),
            _record("tr-new", "new").model_copy(
                update={"retention_until": now + timedelta(days=1)}
            ),
            _record("tr-held", "held").model_copy(
                update={
                    "retention_until": now - timedelta(seconds=1),
                    "legal_hold_until": now + timedelta(days=1),
                }
            ),
        )
    )
    result = await store.prune_expired(now)
    records = await store.query(TranscriptQuery(actor_id=ActorId("actor-1")))
    assert result.deleted_count == 1
    assert tuple(record.content for record in records) == ("held", "new")
    cleanup_request = await _assert_cleanup_dry_run(
        store,
        TranscriptAccessScope(
            actor_id=ActorId("actor-1"),
            space_id=SpaceId("space-1"),
        ),
        now + timedelta(seconds=1),
    )
    await _assert_cleanup_execution(store, db_path, cleanup_request)


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
    db_path = tmp_path / "state.sqlite3"
    store = SQLiteTranscriptStore(db_path)
    now = datetime(2026, 7, 1, tzinfo=UTC)
    try:
        await _assert_prune_and_cleanup_flow(store, db_path, now)
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
