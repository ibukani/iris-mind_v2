"""Relationship / affect persistence boundary architecture guards."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_relationship_and_affect_store_implementations_live_in_adapters() -> None:
    """Relationship / affect store 実装は runtime 配下に置かない。"""
    expected_adapter_paths = (
        "iris/adapters/relationship/memory.py",
        "iris/adapters/relationship/sqlite.py",
        "iris/adapters/affect/memory.py",
        "iris/adapters/affect/sqlite.py",
    )
    forbidden_runtime_paths = (
        "iris/runtime/relationship",
        "iris/runtime/affect",
        "iris/runtime/state/relationship",
        "iris/runtime/state/affect",
    )

    assert all((ROOT / path).exists() for path in expected_adapter_paths)
    assert not any((ROOT / path).exists() for path in forbidden_runtime_paths)


def test_cognitive_steps_depend_on_contract_store_protocols() -> None:
    """Cognitive steps は concrete SQLite store に依存しない。"""
    relationship_step = _read("iris/cognitive/affect/relationship.py")
    affect_step = _read("iris/cognitive/affect/persistence.py")

    assert "iris.contracts.relationship" in relationship_step
    assert "iris.contracts.affect" in affect_step
    assert "iris.adapters" not in relationship_step
    assert "iris.adapters" not in affect_step
    assert "SQLiteRelationshipStore" not in relationship_step
    assert "SQLiteAffectStore" not in affect_step


def test_relationship_and_affect_snapshots_are_not_memory_records() -> None:
    """RelationshipSnapshot / AffectSnapshot を MemoryRecord として保存しない。"""
    memory_write = _read("iris/cognitive/memory/write.py")
    memory_candidates = _read("iris/cognitive/memory/candidates.py")
    relationship_step = _read("iris/cognitive/affect/relationship.py")
    affect_persistence = _read("iris/cognitive/affect/persistence.py")

    assert "RelationshipSnapshotRecord" not in memory_write
    assert "AffectBaselineRecord" not in memory_write
    assert "RelationshipSnapshot" not in memory_candidates
    assert "AffectSnapshot" not in memory_candidates
    assert "MemoryRecord" not in relationship_step
    assert "MemoryRecord" not in affect_persistence


def test_space_id_is_not_relationship_or_affect_owner() -> None:
    """Relationship / affect の durable owner に space_id を使わない。"""
    checked_paths = (
        "iris/contracts/relationship.py",
        "iris/contracts/affect.py",
        "iris/adapters/relationship/memory.py",
        "iris/adapters/relationship/sqlite.py",
        "iris/adapters/affect/memory.py",
        "iris/adapters/affect/sqlite.py",
        "iris/cognitive/affect/relationship.py",
        "iris/cognitive/affect/persistence.py",
    )

    assert all("space_id" not in _read(path) for path in checked_paths)
