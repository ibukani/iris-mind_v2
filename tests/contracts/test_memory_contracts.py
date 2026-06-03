from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from iris.contracts.memory import MemoryId, MemoryQuery, MemoryRecord, MemorySearchResult
from iris.core.ids import UserId


def test_memory_contracts_are_frozen_and_typed() -> None:
    record = MemoryRecord(
        id=MemoryId("memory-1"),
        text="Iris remembers tea preferences.",
        subject_id=UserId("user-1"),
        salience=0.4,
    )
    query = MemoryQuery(text="tea", subject_id=UserId("user-1"), limit=3)
    result = MemorySearchResult(record=record, score=1.0)

    assert record.id == MemoryId("memory-1")
    assert query.limit == 3
    assert result.record.text == "Iris remembers tea preferences."

    with pytest.raises(FrozenInstanceError):
        record.text = "changed"  # type: ignore[misc]
