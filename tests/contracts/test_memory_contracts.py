"""メモリ契約の不変性と型のテスト。"""

from __future__ import annotations

from iris.contracts.memory import MemoryId, MemoryQuery, MemoryRecord, MemorySearchResult
from iris.core.ids import ActorId, SpaceId
from tests.helpers.immutability import assert_frozen_field


def test_memory_contracts_are_frozen_and_typed() -> None:
    """MemoryRecord、MemoryQuery、MemorySearchResultがfrozen dataclassであることを確認する。"""
    record = MemoryRecord(
        id=MemoryId("memory-1"),
        text="Iris remembers tea preferences.",
        actor_id=ActorId("actor-1"),
        space_id=SpaceId("space-1"),
        salience=0.4,
    )
    query = MemoryQuery(
        text="tea",
        actor_id=ActorId("actor-1"),
        space_id=SpaceId("space-1"),
        limit=3,
    )
    result = MemorySearchResult(record=record, score=1.0)

    assert record.id == MemoryId("memory-1")
    assert record.actor_id == ActorId("actor-1")
    assert record.space_id == SpaceId("space-1")
    assert query.actor_id == ActorId("actor-1")
    assert query.space_id == SpaceId("space-1")
    assert query.limit == 3
    assert result.record.text == "Iris remembers tea preferences."
    assert_frozen_field(record, "text", "changed")
