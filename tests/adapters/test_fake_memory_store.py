"""FakeMemoryStoreの決定論的検索とフィルタリングのテスト。"""

from __future__ import annotations

from iris.adapters.memory.fake import FakeMemoryStore
from iris.contracts.memory import MemoryId, MemoryQuery, MemoryRecord, MemorySearchResult
from iris.core.ids import ActorId, SpaceId


def test_fake_memory_store_returns_deterministic_text_matches() -> None:
    """FakeMemoryStoreがトークンの重複に基づいて決定論的にテキスト一致をランク付けすることを確認する。"""
    store = FakeMemoryStore(
        records=(
            MemoryRecord(id=MemoryId("m1"), text="User likes green tea."),
            MemoryRecord(id=MemoryId("m2"), text="User likes tea and quiet mornings."),
            MemoryRecord(id=MemoryId("m3"), text="Unrelated memory."),
        )
    )

    results = store.search(MemoryQuery(text="quiet tea", limit=2))

    assert tuple(result.record.id for result in results) == (MemoryId("m2"), MemoryId("m1"))
    assert tuple(result.score for result in results) == (2.0, 1.0)


def test_fake_memory_store_filters_by_actor_and_supports_put() -> None:
    """FakeMemoryStoreがactor_idで検索結果をフィルタリングし、put()をサポートすることを確認する。"""
    store = FakeMemoryStore()
    store.put(MemoryRecord(id=MemoryId("m1"), text="Alice likes tea.", actor_id=ActorId("alice")))
    store.put(MemoryRecord(id=MemoryId("m2"), text="Bob likes tea.", actor_id=ActorId("bob")))

    results = store.search(MemoryQuery(text="tea", actor_id=ActorId("bob")))

    assert tuple(result.record.id for result in results) == (MemoryId("m2"),)


def test_fake_memory_store_filters_by_space() -> None:
    """FakeMemoryStoreがspace_idで検索結果をフィルタリングすることを確認する。"""
    store = FakeMemoryStore(
        records=(
            MemoryRecord(
                id=MemoryId("m1"), text="Tea in channel one.", space_id=SpaceId("space-1")
            ),
            MemoryRecord(
                id=MemoryId("m2"), text="Tea in channel two.", space_id=SpaceId("space-2")
            ),
        )
    )

    results = store.search(MemoryQuery(text="tea", space_id=SpaceId("space-2")))

    assert tuple(result.record.id for result in results) == (MemoryId("m2"),)


def test_fake_memory_store_can_return_fixed_results() -> None:
    """FakeMemoryStoreが設定時にfixed_resultsを返し、クエリを無視することを確認する。"""
    fixed = MemorySearchResult(
        record=MemoryRecord(id=MemoryId("fixed"), text="Fixed memory."),
        score=0.5,
    )
    store = FakeMemoryStore(fixed_results=(fixed,))

    assert tuple(store.search(MemoryQuery(text="anything"))) == (fixed,)
