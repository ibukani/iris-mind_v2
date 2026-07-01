"""明示的入力だけを保存する決定論的メモリ worker。"""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING

from iris.cognitive.memory.policy import MemoryWritePolicy
from iris.contracts.memory import MemoryId, MemoryRecord
from iris.contracts.memory_candidates import MemoryCandidate
from iris.core.metadata import immutable_metadata
from iris.runtime.learning.jobs import (
    BackgroundJobKind,
    MemoryBackgroundJobPayload,
)

_ERR_INVALID_MEMORY_PAYLOAD = "memory consolidation requires MemoryBackgroundJobPayload"
_ERR_REJECTED_MEMORY = "memory candidate rejected by write policy"

if TYPE_CHECKING:
    from iris.contracts.memory import MutableMemoryStore
    from iris.runtime.learning.jobs import BackgroundJobRecord


class DeterministicMemoryConsolidationWorker:
    """typed payload を再検証し、意味を追加せずメモリへ保存する。"""

    kind = BackgroundJobKind.MEMORY_CONSOLIDATION

    def __init__(
        self,
        store: MutableMemoryStore,
        policy: MemoryWritePolicy | None = None,
    ) -> None:
        """正本メモリストアと hot-path 同等の保存ポリシーを注入する。"""
        self._store = store
        self._policy = policy or MemoryWritePolicy()

    def run(self, job: BackgroundJobRecord) -> None:
        """明示候補だけを決定論的 ID で保存する。

        Raises:
            TypeError: payload 型がメモリジョブ用でない場合。
            ValueError: 保存ポリシーが候補を拒否した場合。
        """
        payload = job.payload
        if not isinstance(payload, MemoryBackgroundJobPayload):
            raise TypeError(_ERR_INVALID_MEMORY_PAYLOAD)
        candidate = MemoryCandidate(
            text=payload.text,
            kind=payload.memory_kind,
            salience=payload.salience,
            confidence=payload.confidence,
            source=payload.source,
            reason=payload.reason,
            retention_policy=payload.retention_policy,
            sensitivity=payload.sensitivity,
            review_required=payload.review_required,
            actor_id=payload.actor_id,
            space_id=payload.space_id,
            source_observation_id=payload.source_observation_id,
        )
        if not self._policy.accept(candidate):
            raise ValueError(_ERR_REJECTED_MEMORY)
        digest = sha256(job.idempotency_key.encode()).hexdigest()
        self._store.update(
            MemoryRecord(
                id=MemoryId(f"learned-{digest[:24]}"),
                text=candidate.text.strip(),
                actor_id=candidate.actor_id,
                space_id=candidate.space_id,
                salience=candidate.salience,
                kind=candidate.kind,
                confidence=candidate.confidence,
                source_observation_id=candidate.source_observation_id,
                created_at=job.created_at,
                updated_at=job.updated_at,
                metadata=immutable_metadata(
                    {
                        "candidate_source": candidate.source.value,
                        "retention_policy": candidate.retention_policy.value,
                        "sensitivity": candidate.sensitivity.value,
                        "review_required": "true" if candidate.review_required else "false",
                        "reason": candidate.reason or "",
                    }
                ),
            )
        )
