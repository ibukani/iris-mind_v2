"""Tests affect-aware one-turn cognitive flow memory relationship context."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.memory.fake import FakeMemoryStore
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.memory import MemoryId, MemoryRecord
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
    wire_affect_memory_aware_cognitive_cycle,
)
from iris.runtime.wiring.llm import wire_response_generator
from tests.helpers.output_pipeline import make_output_pipeline


def actor_message(text: str) -> ActorMessageObservation:
    """Return an ActorMessageObservation text test identity."""
    return ActorMessageObservation(
        observation_id=ObservationId("obs-affect-runtime"),
        session_id=SessionId("session-affect-runtime"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-affect-runtime"),
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
async def test_affect_aware_one_turn_flow_includes_affect_relationship_and_memory_context() -> None:
    """Verify affect-aware flow includes memory, affect, relationship context in prompt."""
    memory_store = FakeMemoryStore(
        records=(
            MemoryRecord(
                id=MemoryId("m1"),
                text="Mina likes jasmine tea.",
                actor_id=ActorId("actor-affect-runtime"),
            ),
        ),
    )
    llm = FakeLLMClient(responses=("affect-aware reply",))
    app = IrisApp(
        output_pipeline=make_output_pipeline(),
        cycle=wire_affect_memory_aware_cognitive_cycle(
            stores=CognitiveCycleStores(
                memory_store=memory_store,
                relationship_store=InMemoryRelationshipStore(),
                affect_store=InMemoryAffectStore(),
            ),
            extension_steps=(ResponseGenerationStep(wire_response_generator(llm)),),
        ),
    )

    output = await app.process_observation(
        actor_message("jasmine tea ありがとう、急ぎで助かった"),
    )
    prompt_messages = llm.requests[0].messages
    system_prompt = prompt_messages[0].content
    context_prompts = "\n\n".join(message.content for message in prompt_messages[1:-1])

    assert output.text == "affect-aware reply"
    assert "Mina likes jasmine tea." not in system_prompt
    assert "Mina likes jasmine tea." in context_prompts
    assert "Affect context:" in context_prompts
    assert "positive VAD" in context_prompts
    assert "Relationship context:" in context_prompts
    assert "Mina: neutral relationship" in context_prompts
