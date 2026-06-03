from __future__ import annotations

from collections.abc import Callable, Sequence
from math import sqrt

from iris.adapters.memory.ports import MemoryStore
from iris.contracts.memory import MemoryQuery, MemoryRecord, MemorySearchResult

EmbeddingFunction = Callable[[str], Sequence[float]]


class InMemoryVectorMemoryStore(MemoryStore):
    """Deterministic in-memory vector MemoryStore for adapter tests and local wiring."""

    def __init__(
        self,
        embed_text: EmbeddingFunction,
        records: Sequence[MemoryRecord] = (),
    ) -> None:
        self._embed_text = embed_text
        self._entries: list[tuple[MemoryRecord, tuple[float, ...]]] = []
        for record in records:
            self.put(record)

    def put(self, record: MemoryRecord) -> None:
        self._entries.append((record, _vector_from_embedding(self._embed_text(record.text))))

    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        if query.limit <= 0:
            return ()

        query_vector = _vector_from_embedding(self._embed_text(query.text))
        ranked: list[tuple[float, int, MemorySearchResult]] = []
        for index, (record, record_vector) in enumerate(self._entries):
            if query.subject_id is not None and record.subject_id != query.subject_id:
                continue
            score = _cosine_similarity(query_vector, record_vector)
            ranked.append((score, index, MemorySearchResult(record=record, score=score)))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return tuple(result for _, _, result in ranked[: query.limit])


def _vector_from_embedding(values: Sequence[float]) -> tuple[float, ...]:
    vector = tuple(float(value) for value in values)
    if not vector:
        raise ValueError("Embedding function must return at least one dimension.")
    return vector


def _cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("Embedding function must return vectors with stable dimensions.")

    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0

    dot_product = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
    return dot_product / (left_norm * right_norm)
