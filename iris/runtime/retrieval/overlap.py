"""Embedding similarity による bounded memory overlap detection。"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import TYPE_CHECKING

from iris.contracts.embeddings import EmbeddingBatchRequest
from iris.contracts.retrieval import RetrievalOverlapItem, RetrievalSourceKind

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.contracts.embeddings import EmbeddingClient
    from iris.contracts.memory import MemoryRecord


_MIN_OVERLAP_CANDIDATES = 2


@dataclass(frozen=True)
class MemoryOverlapDetectionPolicy:
    """Overlap detection の候補数と similarity 閾値。"""

    max_candidates: int = 32
    similarity_threshold: float = 0.92
    model_slot: str | None = "memory_overlap_detection"

    def __post_init__(self) -> None:
        """Policy 値を検証する。

        Raises:
            ValueError: 候補数または similarity 閾値が範囲外の場合。
        """
        if self.max_candidates < 0:
            msg = "max_candidates must be >= 0"
            raise ValueError(msg)
        if not -1.0 <= self.similarity_threshold <= 1.0:
            msg = "similarity_threshold must be between -1.0 and 1.0"
            raise ValueError(msg)


def detect_memory_overlaps(
    records: Sequence[MemoryRecord],
    embedding_client: EmbeddingClient,
    policy: MemoryOverlapDetectionPolicy | None = None,
) -> tuple[RetrievalOverlapItem, ...]:
    """Bounded records から embedding similarity overlap を検出する。

    Args:
        records: canonical durable memory records。
        embedding_client: provider-neutral embedding port。
        policy: 候補数と similarity 閾値。

    Returns:
        similarity threshold 以上の memory pair。
    """
    active_policy = policy or MemoryOverlapDetectionPolicy()
    candidates = tuple(records[: active_policy.max_candidates])
    if len(candidates) < _MIN_OVERLAP_CANDIDATES:
        return ()
    batch = embedding_client.embed_text_batch(
        EmbeddingBatchRequest(
            texts=tuple(record.text for record in candidates),
            model_slot=active_policy.model_slot,
            metadata={"stage": "memory_overlap_detection"},
        )
    )
    overlaps: list[RetrievalOverlapItem] = []
    for left_index, left in enumerate(candidates):
        for right_index in range(left_index + 1, len(candidates)):
            score = _cosine(
                batch.embeddings[left_index].vector,
                batch.embeddings[right_index].vector,
            )
            if score >= active_policy.similarity_threshold:
                overlaps.append(
                    RetrievalOverlapItem(
                        left_source_id=str(left.id),
                        right_source_id=str(candidates[right_index].id),
                        source_kind=RetrievalSourceKind.DURABLE_MEMORY,
                        score=score,
                        reason="embedding similarity overlap",
                        model_metadata=batch.model_metadata,
                    )
                )
    return tuple(overlaps)


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        msg = "Embedding dimensions must match for overlap detection"
        raise ValueError(msg)
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    dot = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
    return dot / (left_norm * right_norm)
