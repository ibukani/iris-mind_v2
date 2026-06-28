"""Memory / relationship / affect の durable runtime flow テスト。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.persistence.sqlite.stores.affect import SQLiteAffectStore
from iris.adapters.persistence.sqlite.stores.memory import SQLiteMemoryStore
from iris.adapters.persistence.sqlite.stores.relationship import SQLiteRelationshipStore
from iris.contracts.affect import AffectBaselineRecord
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.memory import MemoryQuery
from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.contracts.relationship import RelationshipSnapshotRecord
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId
from iris.features.chat.definition import define_chat_feature
from iris.runtime.app import IrisApp
from iris.runtime.wiring.cognitive import (
    CognitiveCycleStores,
    wire_core_cognitive_cycle,
)
from iris.runtime.wiring.features import collect_cognitive_steps
from iris.runtime.wiring.llm import wire_response_generator
from tests.helpers.output_pipeline import make_output_pipeline

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path


_ACTOR_ID = ActorId("actor-durable-owner")


def _actor() -> Identity:
    return Identity(
        actor_id=_ACTOR_ID,
        actor_kind=ActorKind.HUMAN,
        display_name="Mina",
        provider="test",
        provider_subject=ExternalRef("mina"),
    )


def _message(observation_id: str, text: str) -> ActorMessageObservation:
    return ActorMessageObservation(
        observation_id=ObservationId(observation_id),
        session_id=SessionId("session-durable-flow"),
        context=ObservationContext(actor=_actor()),
        occurred_at=datetime(2026, 6, 24, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )


@asynccontextmanager
async def _app_with_stores(
    *,
    db_path: Path,
    llm: FakeLLMClient,
) -> AsyncGenerator[IrisApp]:
    memory_store = SQLiteMemoryStore(db_path)
    relationship_store = SQLiteRelationshipStore(db_path)
    affect_store = SQLiteAffectStore(db_path)
    try:
        yield IrisApp(
            output_pipeline=make_output_pipeline(),
            cycle=wire_core_cognitive_cycle(
                stores=CognitiveCycleStores(
                    memory_store=memory_store,
                    relationship_store=relationship_store,
                    affect_store=affect_store,
                ),
                extension_steps=collect_cognitive_steps(
                    [define_chat_feature(wire_response_generator(llm))]
                ),
            ),
        )
    finally:
        memory_store.close()
        await relationship_store.close()
        await affect_store.close()


@pytest.mark.anyio
async def test_memory_relationship_affect_survive_sqlite_turn_reload(
    tmp_path: Path,
) -> None:
    """Memory は検索対象、relationship/affect は別 state として SQLite に残る。"""
    db_path = tmp_path / "state.db"
    llm = FakeLLMClient(responses=("stored", "retrieved"))

    async with _app_with_stores(db_path=db_path, llm=llm) as app1:
        output1 = await app1.process_observation(
            _message("obs-durable-1", "覚えて: jasmine tea favorite. thanks"),
        )

    reloaded_memory = SQLiteMemoryStore(db_path)
    reloaded_relationship = SQLiteRelationshipStore(db_path)
    reloaded_affect = SQLiteAffectStore(db_path)
    records = reloaded_memory.filter(MemoryQuery(text="", include_archived=True))
    relationship = await reloaded_relationship.get(_ACTOR_ID)
    affect = await reloaded_affect.get_global()

    async with _app_with_stores(db_path=db_path, llm=llm) as app2:
        output2 = await app2.process_observation(
            _message("obs-durable-2", "what tea do I like?"),
        )

    second_prompt = llm.requests[1].messages[-1].content

    assert output1.text == "stored"
    assert output2.text == "retrieved"
    assert any("jasmine tea" in record.text for record in records)
    assert all(record.actor_id == _ACTOR_ID for record in records)
    assert all(record.space_id is None for record in records)
    assert relationship is not None
    assert relationship.actor_id == _ACTOR_ID
    assert relationship.source_observation_id == ObservationId("obs-durable-1")
    assert affect is not None
    assert affect.scope == "global"
    assert affect.actor_id is None
    assert affect.source_observation_id == ObservationId("obs-durable-1")
    assert "jasmine tea" in second_prompt

    reloaded_memory.close()
    await reloaded_relationship.close()
    await reloaded_affect.close()


@pytest.mark.anyio
async def test_reloaded_affect_baseline_is_visible_to_response_prompt(
    tmp_path: Path,
) -> None:
    """SQLite に保存された affect baseline は runtime reload 後の prompt に入る。"""
    db_path = tmp_path / "state.db"

    async with _app_with_stores(
        db_path=db_path,
        llm=FakeLLMClient(responses=("stored",)),
    ) as app1:
        await app1.process_observation(_message("obs-affect-reload-1", "thanks, I am happy"))

    store = SQLiteAffectStore(db_path)
    baseline = await store.get_global()
    assert baseline is not None
    assert baseline.affect_summary is not None
    await store.close()

    reloaded_llm = FakeLLMClient(responses=("reloaded",))
    async with _app_with_stores(
        db_path=db_path,
        llm=reloaded_llm,
    ) as app2:
        await app2.process_observation(
            _message("obs-affect-reload-2", "what tea do I like?"),
        )

    assert reloaded_llm.requests
    prompt_text = "\n".join(message.content for message in reloaded_llm.requests[-1].messages)
    assert "Affect context:" in prompt_text
    assert "VAD" in prompt_text


def test_relationship_and_affect_records_are_not_space_owned() -> None:
    """Relationship / affect durable state は space_id を owner field にしない。"""
    relationship_fields = set(RelationshipSnapshotRecord.model_fields)
    affect_fields = set(AffectBaselineRecord.model_fields)

    assert "space_id" not in relationship_fields
    assert "space_id" not in affect_fields
