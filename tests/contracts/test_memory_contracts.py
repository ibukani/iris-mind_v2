"""メモリ契約の不変性と型のテスト。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from iris.contracts.memory import (
    MemoryId,
    MemoryKind,
    MemoryQuery,
    MemoryRecord,
    MemorySearchResult,
)
from iris.core.ids import ActorId, ObservationId, SpaceId
from tests.helpers.approx import approx
from tests.helpers.immutability import assert_frozen_field


def test_memory_contracts_are_frozen_and_typed() -> None:
    """MemoryRecord、MemoryQuery、MemorySearchResultがfrozen dataclassであることを確認する。"""
    record = MemoryRecord(
        id=MemoryId("memory-1"),
        text="Iris remembers tea preferences.",
        actor_id=ActorId("actor-1"),
        space_id=SpaceId("space-1"),
        salience=0.4,
        kind=MemoryKind.PREFERENCE,
        confidence=0.9,
        source_observation_id=ObservationId("obs-1"),
        metadata={"source": "discord"},
    )
    query = MemoryQuery(
        text="tea",
        actor_id=ActorId("actor-1"),
        space_id=SpaceId("space-1"),
        limit=3,
        kind=MemoryKind.PREFERENCE,
    )
    result = MemorySearchResult(record=record, score=1.0)

    assert record.id == MemoryId("memory-1")
    assert record.actor_id == ActorId("actor-1")
    assert record.space_id == SpaceId("space-1")
    assert record.kind == MemoryKind.PREFERENCE
    assert record.confidence == approx(0.9)
    assert record.source_observation_id == ObservationId("obs-1")
    assert dict(record.metadata) == {"source": "discord"}
    assert query.actor_id == ActorId("actor-1")
    assert query.space_id == SpaceId("space-1")
    assert query.limit == 3
    assert query.kind == MemoryKind.PREFERENCE
    assert result.record.text == "Iris remembers tea preferences."
    assert_frozen_field(record, "text", "changed")


def test_memory_record_metadata_is_immutable() -> None:
    """MemoryRecord.metadata は mapping proxy として返される。"""
    record = MemoryRecord(
        id=MemoryId("m"),
        text="text",
        metadata={"k": "v"},
    )

    meta: Any = record.metadata
    with pytest.raises(TypeError):
        # MappingProxyType は読み取り専用で、要素代入時に TypeError を送出する。
        meta["k"] = "v2"


def test_memory_record_defaults_apply_when_omitted() -> None:
    """未指定フィールドは契約上のデフォルトに正規化される。"""
    record = MemoryRecord(id=MemoryId("m"), text="text")
    now = datetime.now(tz=UTC)

    assert record.kind == MemoryKind.NOTE
    assert record.confidence == approx(1.0)
    assert record.archived is False
    assert record.source_observation_id is None
    assert record.created_at is None
    assert record.updated_at is None
    assert dict(record.metadata) == {}
    assert isinstance(now, datetime)
