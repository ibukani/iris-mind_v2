"""Project context / transcript の bounded runtime retrieval。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from iris.contracts.prompting import PromptSectionKind
from iris.contracts.retrieval import (
    ProjectContextQuery,
    ProjectContextStore,
    RetrievalFallbackReason,
    RetrievalObservability,
    RetrievalPipelineResult,
    RetrievalQuery,
    RetrievalSourceKind,
    RetrievalSourceScope,
    RetrievedContextItem,
)
from iris.contracts.transcript import TranscriptQuery
from iris.core.datetime_utils import now_utc
from iris.runtime.config.prompt_budget import (
    RuntimePromptBudgetConfig,
    project_context_top_k_for_profile,
)
from iris.runtime.observability.logger import LoguruRuntimeLogger

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from iris.runtime.observability.ports import RuntimeLogger
    from iris.runtime.state.transcript import TranscriptStore


class RuntimeSourceRetrievalPipeline:
    """共有 source contract へ project / transcript を bounded に供給する。"""

    def __init__(
        self,
        *,
        project_context_store: ProjectContextStore,
        transcript_store: TranscriptStore,
        prompt_budget_config: RuntimePromptBudgetConfig,
        max_total_items: int = 12,
        runtime_logger: RuntimeLogger | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        """Source store、prompt budget、clock を明示注入する。"""
        self._project_context_store = project_context_store
        self._transcript_store = transcript_store
        self._prompt_budget_config = prompt_budget_config
        self._max_total_items = max(0, max_total_items)
        self._logger = runtime_logger or LoguruRuntimeLogger()
        self._now = now or now_utc

    async def retrieve(self, query: RetrievalQuery) -> RetrievalPipelineResult:
        """認可 scope 内の source を同時取得し、bounded result を返す。

        Returns:
            共通 source contract に正規化された bounded result。
        """
        if not query.text.strip():
            return _empty_result(RetrievalFallbackReason.EMPTY_QUERY)

        profile = query.profile
        total_limit = min(query.max_total_items, self._max_total_items)
        project_limit = min(
            project_context_top_k_for_profile(self._prompt_budget_config, profile),
            total_limit,
        )
        task_budget = self._prompt_budget_config.profile_budget(profile).section_budget(
            PromptSectionKind.TASK_CONTEXT
        )
        transcript_limit = min(task_budget.max_items, total_limit)
        project_result, transcript_result = await asyncio.gather(
            self._retrieve_projects(query, project_limit),
            self._retrieve_transcript(query, transcript_limit),
        )
        items = (*project_result.items, *transcript_result.items)[:total_limit]
        fallback = _first_fallback(project_result, transcript_result, items)
        result = RetrievalPipelineResult(
            items=items,
            prompt_section=None,
            observability=RetrievalObservability(
                retrieved_count=(
                    project_result.observability.retrieved_count
                    + transcript_result.observability.retrieved_count
                ),
                reranked_count=0,
                selected_count=len(items),
                fallback_reason=fallback,
                source_counts=_source_counts(items),
            ),
        )
        self._logger.info(
            "runtime.retrieval.sources",
            retrieved_count=result.observability.retrieved_count,
            selected_count=result.observability.selected_count,
            project_count=sum(
                1 for item in items if item.source_kind is RetrievalSourceKind.PROJECT_CONTEXT
            ),
            transcript_count=sum(
                1 for item in items if item.source_kind is RetrievalSourceKind.TRANSCRIPT
            ),
            fallback_reason=fallback.value if fallback is not None else None,
        )
        return result

    async def _retrieve_projects(
        self,
        query: RetrievalQuery,
        limit: int,
    ) -> RetrievalPipelineResult:
        if limit == 0 or query.scope.space_id is None:
            return _empty_result(RetrievalFallbackReason.QUERY_LIMIT_ZERO)
        try:
            records = await asyncio.to_thread(
                self._project_context_store.query,
                ProjectContextQuery(
                    text=query.text,
                    actor_id=query.scope.actor_id,
                    account_id=query.scope.account_id,
                    space_id=query.scope.space_id,
                    limit=limit,
                ),
            )
        except (OSError, RuntimeError, ValueError):
            return _empty_result(RetrievalFallbackReason.VECTOR_INDEX_UNAVAILABLE)
        items = tuple(
            RetrievedContextItem(
                source_id=record.context_id,
                source_kind=RetrievalSourceKind.PROJECT_CONTEXT,
                prompt_section_kind=PromptSectionKind.PROJECT_MEMORY,
                text=record.text,
                score=_text_relevance(query.text, record.text),
                reason="bounded project context match",
                scope=query.scope,
                metadata=record.metadata,
            )
            for record in records
        )
        return _source_result(items, len(records))

    async def _retrieve_transcript(
        self,
        query: RetrievalQuery,
        limit: int,
    ) -> RetrievalPipelineResult:
        scope = query.scope
        if limit == 0 or not any(
            value is not None for value in (scope.actor_id, scope.account_id, scope.space_id)
        ):
            return _empty_result(RetrievalFallbackReason.QUERY_LIMIT_ZERO)
        try:
            records = await self._transcript_store.query(
                TranscriptQuery(
                    actor_id=scope.actor_id,
                    account_id=scope.account_id,
                    space_id=scope.space_id,
                    session_id=scope.session_id,
                    limit=limit,
                )
            )
        except (OSError, RuntimeError, TimeoutError, ValueError):
            return _empty_result(RetrievalFallbackReason.VECTOR_INDEX_UNAVAILABLE)
        current = self._now()
        bounded = tuple(
            record
            for record in records
            if record.retention_until is None or record.retention_until > current
        )
        relevant = tuple(
            record for record in bounded if _text_relevance(query.text, record.content) > 0.0
        )
        items = tuple(
            RetrievedContextItem(
                source_id=str(record.transcript_id),
                source_kind=RetrievalSourceKind.TRANSCRIPT,
                prompt_section_kind=PromptSectionKind.TASK_CONTEXT,
                text=f"{record.role.value}: {record.content}",
                score=_text_relevance(query.text, record.content),
                reason="scoped transcript match",
                scope=RetrievalSourceScope(
                    actor_id=record.actor_id,
                    account_id=record.account_id,
                    space_id=record.space_id,
                    session_id=record.session_id,
                ),
                metadata=record.metadata,
            )
            for record in relevant
        )
        return _source_result(items, len(records))


def _text_relevance(query: str, text: str) -> float:
    query_tokens = frozenset(query.casefold().split())
    text_tokens = frozenset(text.casefold().split())
    if query_tokens and text_tokens:
        overlap = len(query_tokens & text_tokens) / len(query_tokens)
        if overlap > 0.0:
            return overlap
    return 1.0 if query.casefold() in text.casefold() else 0.0


def _source_result(
    items: tuple[RetrievedContextItem, ...],
    retrieved_count: int,
) -> RetrievalPipelineResult:
    return RetrievalPipelineResult(
        items=items,
        prompt_section=None,
        observability=RetrievalObservability(
            retrieved_count=retrieved_count,
            reranked_count=0,
            selected_count=len(items),
            source_counts=_source_counts(items),
        ),
    )


def _empty_result(reason: RetrievalFallbackReason) -> RetrievalPipelineResult:
    return RetrievalPipelineResult(
        items=(),
        prompt_section=None,
        observability=RetrievalObservability(
            retrieved_count=0,
            reranked_count=0,
            selected_count=0,
            fallback_reason=reason,
        ),
    )


def _first_fallback(
    project: RetrievalPipelineResult,
    transcript: RetrievalPipelineResult,
    items: tuple[RetrievedContextItem, ...],
) -> RetrievalFallbackReason | None:
    if items:
        return None
    return project.observability.fallback_reason or transcript.observability.fallback_reason


def _source_counts(
    items: tuple[RetrievedContextItem, ...],
) -> tuple[tuple[RetrievalSourceKind, int], ...]:
    return tuple(
        (kind, sum(1 for item in items if item.source_kind is kind))
        for kind in RetrievalSourceKind
        if any(item.source_kind is kind for item in items)
    )
