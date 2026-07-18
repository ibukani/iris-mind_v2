"""メモリ候補を canonical store へ書かず review boundary へ統合する worker。"""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING

from iris.cognitive.memory.consolidation import (
    MemoryConsolidationPolicy,
    consolidate_memory_candidates,
)
from iris.contracts.memory_candidates import (
    MemoryCandidate,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.contracts.memory_consolidation import (
    MemoryConsolidationJobPayload,
    MemoryConsolidationSourceCandidate,
)
from iris.contracts.review_candidates import ReviewCandidateType
from iris.core.datetime_utils import now_utc
from iris.core.metadata import immutable_metadata
from iris.runtime.learning.jobs import (
    BackgroundJobKind,
    MemoryBackgroundJobPayload,
)
from iris.runtime.state.memory_candidates import (
    MemoryCandidateReviewId,
    MemoryCandidateReviewRecord,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from iris.runtime.learning.jobs import BackgroundJobRecord
    from iris.runtime.state.memory_candidates import MemoryCandidateReviewStore


_ERR_INVALID_MEMORY_PAYLOAD = "memory consolidation requires a typed consolidation payload"


class DeterministicMemoryConsolidationWorker:
    """候補を dedupe し、結果を review store に冪等保存する。"""

    kind = BackgroundJobKind.MEMORY_CONSOLIDATION

    def __init__(
        self,
        store: MemoryCandidateReviewStore,
        *,
        policy: MemoryConsolidationPolicy | None = None,
        now: Callable[[], datetime] = now_utc,
    ) -> None:
        """Review store、deterministic policy、clock を注入する。"""
        self._store = store
        self._policy = policy or MemoryConsolidationPolicy()
        self._now = now

    def run(self, job: BackgroundJobRecord) -> None:
        """候補を統合し、canonical memory ではなく review boundary へ保存する。"""
        candidates = _source_candidates(job)
        for result in consolidate_memory_candidates(
            candidates,
            now=self._now(),
            policy=self._policy,
        ):
            proposed = result.proposed
            candidate_metadata = dict(proposed.metadata)
            candidate_metadata.update(
                {
                    "consolidation_decision": result.decision_kind.value,
                    "source_candidate_ids": "|".join(result.source_candidate_ids),
                    "supersedes_candidate_ids": "|".join(result.supersedes_candidate_ids),
                    "consolidation_reason": result.reason,
                }
            )
            candidate = MemoryCandidate(
                text=proposed.text.strip(),
                kind=proposed.kind,
                salience=proposed.salience,
                confidence=result.confidence,
                source=MemoryCandidateSource.CONSOLIDATION,
                reason=result.reason,
                retention_policy=MemoryRetentionPolicy.REVIEW_REQUIRED,
                sensitivity=proposed.sensitivity,
                review_required=True,
                actor_id=proposed.actor_id,
                space_id=proposed.space_id,
                source_observation_id=proposed.source_observation_id,
                metadata=immutable_metadata(candidate_metadata),
            )
            record = MemoryCandidateReviewRecord(
                candidate_id=MemoryCandidateReviewId(result.candidate_id),
                candidate=candidate,
                created_at=job.created_at,
                updated_at=job.updated_at,
                idempotency_key=_record_idempotency_key(job, result.candidate_id),
                candidate_type=ReviewCandidateType.CONSOLIDATION,
                actor_id=proposed.actor_id,
                account_id=proposed.account_id,
                space_id=proposed.space_id,
                source_observation_id=proposed.source_observation_id,
                metadata=immutable_metadata(
                    {
                        "source": MemoryCandidateSource.CONSOLIDATION.value,
                        "consolidation_decision": result.decision_kind.value,
                        "source_candidate_ids": "|".join(result.source_candidate_ids),
                        "supersedes_candidate_ids": "|".join(result.supersedes_candidate_ids),
                    }
                ),
            )
            self._store.add_nowait(record)


def _source_candidates(
    job: BackgroundJobRecord,
) -> tuple[MemoryConsolidationSourceCandidate, ...]:
    """Job payload を consolidation source candidate 列へ変換する。

    Returns:
        統合対象の source candidate 列。

    Raises:
        TypeError: payload が consolidation worker の typed contract でない場合。
    """
    payload = job.payload
    if isinstance(payload, MemoryConsolidationJobPayload):
        return payload.candidates
    if isinstance(payload, MemoryBackgroundJobPayload):
        return (_source_candidate_from_legacy_payload(job, payload),)
    raise TypeError(_ERR_INVALID_MEMORY_PAYLOAD)


def _source_candidate_from_legacy_payload(
    job: BackgroundJobRecord,
    payload: MemoryBackgroundJobPayload,
) -> MemoryConsolidationSourceCandidate:
    source_candidate_id = f"source-{sha256(job.idempotency_key.encode()).hexdigest()[:24]}"
    return MemoryConsolidationSourceCandidate(
        source_candidate_id=source_candidate_id,
        text=payload.text,
        kind=payload.memory_kind,
        salience=payload.salience,
        confidence=payload.confidence,
        source=payload.source,
        reason=payload.reason,
        retention_policy=payload.retention_policy,
        sensitivity=payload.sensitivity,
        actor_id=payload.actor_id,
        account_id=payload.account_id,
        space_id=payload.space_id,
        source_observation_id=payload.source_observation_id,
        created_at=job.created_at,
    )


def _record_idempotency_key(job: BackgroundJobRecord, candidate_id: str) -> str:
    material = f"{job.idempotency_key}|{candidate_id}"
    return sha256(material.encode()).hexdigest()
