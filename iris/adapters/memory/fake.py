from __future__ import annotations

from collections.abc import Sequence

from iris.adapters.memory.ports import MemoryStore
from iris.contracts.memory import MemoryQuery, MemoryRecord, MemorySearchResult


class FakeMemoryStore(MemoryStore):
    def __init__(
        self,
        records: Sequence[MemoryRecord] = (),
        *,
        fixed_results: Sequence[MemorySearchResult] | None = None,
    ) -> None:
        self._records = list(records)
        self._fixed_results = tuple(fixed_results) if fixed_results is not None else None

    def put(self, record: MemoryRecord) -> None:
        self._records.append(record)

    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        if self._fixed_results is not None:
            return self._fixed_results[: query.limit]

        terms = tuple(term.casefold() for term in query.text.split() if term.strip())
        ranked: list[tuple[int, int, MemorySearchResult]] = []
        for index, record in enumerate(self._records):
            if query.subject_id is not None and record.subject_id != query.subject_id:
                continue
            score = _score_record(record, terms)
            if score <= 0:
                continue
            ranked.append((score, index, MemorySearchResult(record=record, score=float(score))))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return tuple(result for _, _, result in ranked[: query.limit])


def _score_record(record: MemoryRecord, terms: tuple[str, ...]) -> int:
    if not terms:
        return 0
    text = record.text.casefold()
    return sum(1 for term in terms if term in text)
