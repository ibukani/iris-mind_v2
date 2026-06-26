"""Memory write → retrieval 2-turn persistence flow tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.memory import MemoryQuery
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId
from iris.runtime.app import IrisApp
from iris.runtime.wiring.cognitive import (
    wire_policy_affect_memory_aware_text_response_cognitive_cycle,
)


def _actor_message(text: str) -> ActorMessageObservation:
    """Return an ActorMessageObservation with the given text and a test identity."""
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
        cycle=wire_policy_affect_memory_aware_text_response_cognitive_cycle(
            memory_store=memory_store,
            llm_client=llm,
        )
    )

    # Turn 1: explicit remember request should trigger memory write
    output1 = await app.process_observation(_actor_message("覚えて: jasmine tea is my favorite"))
    assert output1.text == "saved"

    # Turn 2: retrieval should include the previously written memory
    output2 = await app.process_observation(_actor_message("what tea do I like?"))
    assert output2.text == "how about jasmine tea?"

    # Verify the memory was persisted
    records = memory_store.filter(MemoryQuery(text="", include_archived=True))
    assert any("jasmine tea" in r.text for r in records)

    # Verify the memory appeared in the second turn's LLM prompt
    second_prompt = llm.requests[1].messages[-1].content
    assert "jasmine tea" in second_prompt
