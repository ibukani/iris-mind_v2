"""Memory write → retrieval 2-turn persistence flow tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.memory import MemoryQuery
from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId
from iris.features.chat.definition import ResponseGenerationStep
from iris.runtime.app import IrisApp
from iris.runtime.state.ephemeral.affect import InMemoryAffectStore
from iris.runtime.state.ephemeral.relationship import InMemoryRelationshipStore
from iris.runtime.wiring.cognitive import (
    CognitiveCycleStores,
    wire_core_cognitive_cycle,
)
from iris.runtime.wiring.llm import wire_response_generator
from tests.helpers.output_pipeline import make_output_pipeline


def _actor_message(text: str) -> ActorMessageObservation:
    """Return ActorMessageObservation text test identity."""
    return ActorMessageObservation(
        observation_id=ObservationId("obs-write-flow"),
        session_id=SessionId("session-write-flow"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-write-flow"),
                actor_kind=ActorKind.HUMAN,
                display_name="Mina",
                provider="test",
                provider_subject=ExternalRef("mina"),
            ),
        ),
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )


@pytest.mark.anyio
async def test_two_turn_memory_write_then_retrieval_flow() -> None:
    """2ターン目で1ターン目に保存した Memory が取得できることを確認する。"""
    memory_store = InMemoryMemoryStore()
    llm = FakeLLMClient(responses=("saved", "how about jasmine tea?"))
    app = IrisApp(
        output_pipeline=make_output_pipeline(),
        cycle=wire_core_cognitive_cycle(
            stores=CognitiveCycleStores(
                memory_store=memory_store,
                relationship_store=InMemoryRelationshipStore(),
                affect_store=InMemoryAffectStore(),
            ),
            extension_steps=(ResponseGenerationStep(wire_response_generator(llm)),),
        ),
    )

    output1 = await app.process_observation(_actor_message("覚えて: jasmine tea favorite"))
    output2 = await app.process_observation(_actor_message("what tea do I like?"))

    records = memory_store.filter(MemoryQuery(text="", include_archived=True))
    second_prompt = llm.requests[1].messages[-1].content

    assert output1.text == "saved"
    assert output2.text == "how about jasmine tea?"
    assert any("jasmine tea" in record.text for record in records)
    assert "jasmine tea" in second_prompt
