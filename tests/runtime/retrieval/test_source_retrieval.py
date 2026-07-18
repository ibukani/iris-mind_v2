"""Project context / transcript retrieval tests。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from iris.contracts.retrieval import (
    ProjectContextRecord,
    RetrievalQuery,
    RetrievalSourceKind,
    RetrievalSourceScope,
)
from iris.contracts.transcript import (
    TranscriptPruneResult,
    TranscriptQuery,
    TranscriptRecord,
    TranscriptRole,
    TranscriptSource,
    TranscriptSubjectKind,
)
from iris.core.ids import AccountId, ActorId, SessionId, SpaceId, TranscriptId
from iris.runtime.config.prompt_budget import RuntimePromptBudgetConfig
from iris.runtime.retrieval.sources import RuntimeSourceRetrievalPipeline
from iris.runtime.state.project_context import InMemoryProjectContextStore


class _TranscriptStore:
    def __init__(self, records: tuple[TranscriptRecord, ...]) -> None:
        self.records = records
        self.queries: list[TranscriptQuery] = []

    async def query(self, query: TranscriptQuery) -> tuple[TranscriptRecord, ...]:
        self.queries.append(query)
        return self.records[: query.limit]

    async def append(self, records: tuple[TranscriptRecord, ...]) -> None:
        self.records = (*self.records, *records)

    async def prune_expired(self, now: datetime) -> TranscriptPruneResult:
        if now.tzinfo is None:
            return TranscriptPruneResult(deleted_count=0)
        return TranscriptPruneResult(deleted_count=0)


@pytest.mark.asyncio
async def test_source_pipeline_merges_bounded_project_and_transcript_context() -> None:
    """共通 source contract が scope と source kind を保ったまま merge する。"""
    now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    actor_id = ActorId("actor-1")
    account_id = AccountId("account-1")
    space_id = SpaceId("space-1")
    session_id = SessionId("session-1")
    project_store = InMemoryProjectContextStore(now=lambda: now)
    project_store.put(
        ProjectContextRecord(
            context_id="project-tea",
            text="tea project notes",
            space_id=space_id,
            account_id=account_id,
        )
    )
    project_store.put(
        ProjectContextRecord(
            context_id="other-space",
            text="tea in another space",
            space_id=SpaceId("space-2"),
        )
    )
    transcript_store = _TranscriptStore(
        (
            TranscriptRecord(
                transcript_id=TranscriptId("transcript-tea"),
                subject_kind=TranscriptSubjectKind.ACTOR,
                subject_id=str(actor_id),
                role=TranscriptRole.USER,
                source=TranscriptSource.INLINE_RESPONSE,
                content="tea plan from yesterday",
                occurred_at=now - timedelta(days=1),
                recorded_at=now - timedelta(days=1),
                session_id=session_id,
                actor_id=actor_id,
                account_id=account_id,
                space_id=space_id,
                retention_until=now + timedelta(days=1),
            ),
        )
    )
    pipeline = RuntimeSourceRetrievalPipeline(
        project_context_store=project_store,
        transcript_store=transcript_store,
        prompt_budget_config=RuntimePromptBudgetConfig(),
        now=lambda: now,
    )

    result = await pipeline.retrieve(
        RetrievalQuery(
            text="tea",
            scope=RetrievalSourceScope(
                actor_id=actor_id,
                account_id=account_id,
                space_id=space_id,
                session_id=session_id,
            ),
            max_total_items=2,
        )
    )

    assert len(result.items) == 2
    assert {item.source_kind for item in result.items} == {
        RetrievalSourceKind.PROJECT_CONTEXT,
        RetrievalSourceKind.TRANSCRIPT,
    }
    assert all(item.scope.space_id == space_id for item in result.items)
    assert result.observability.selected_count == 2
    assert result.observability.source_counts
    assert transcript_store.queries[0].space_id == space_id
    empty_scope = await pipeline.retrieve(RetrievalQuery(text="tea"))
    assert empty_scope.items == ()
    assert len(transcript_store.queries) == 1
