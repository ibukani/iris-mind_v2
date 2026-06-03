from __future__ import annotations

from iris.adapters.memory.fake import FakeMemoryStore
from iris.contracts.memory import MemoryId, MemoryQuery, MemoryRecord, MemorySearchResult
from iris.core.ids import UserId


def test_fake_memory_store_returns_deterministic_text_matches() -> None:
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


def test_fake_memory_store_filters_by_subject_and_supports_put() -> None:
    store = FakeMemoryStore()
    store.put(MemoryRecord(id=MemoryId("m1"), text="Alice likes tea.", subject_id=UserId("alice")))
    store.put(MemoryRecord(id=MemoryId("m2"), text="Bob likes tea.", subject_id=UserId("bob")))

    results = store.search(MemoryQuery(text="tea", subject_id=UserId("bob")))

    assert tuple(result.record.id for result in results) == (MemoryId("m2"),)


def test_fake_memory_store_can_return_fixed_results() -> None:
    fixed = MemorySearchResult(
        record=MemoryRecord(id=MemoryId("fixed"), text="Fixed memory."),
        score=0.5,
    )
    store = FakeMemoryStore(fixed_results=(fixed,))

    assert tuple(store.search(MemoryQuery(text="anything"))) == (fixed,)
