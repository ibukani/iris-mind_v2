# Copyright 2025 Iris Mind
"""Tests policy-aware one-turn cognitive flow constraints."""

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
from iris.features.chat.definition import define_chat_feature
from iris.runtime.app import IrisApp
from iris.runtime.state.ephemeral.affect import InMemoryAffectStore
from iris.runtime.state.ephemeral.relationship import InMemoryRelationshipStore
from iris.runtime.wiring.cognitive import (
    CognitiveCycleStores,
    wire_core_cognitive_cycle,
)
from iris.runtime.wiring.features import collect_cognitive_steps
from iris.runtime.wiring.llm import wire_response_generator
from tests.helpers.output_pipeline import make_output_pipeline


def _actor_message(text: str) -> ActorMessageObservation:
    """Return ActorMessageObservation text test identity."""
    return ActorMessageObservation(
        observation_id=ObservationId("obs-policy-runtime"),
        session_id=SessionId("session-policy-runtime"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-policy-runtime"),
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
async def test_policy_aware_one_turn_flow_includes_policy_context() -> None:
    """Verify policy-aware flow policy constraints in LLM prompt."""
    memory_store = FakeMemoryStore(
        records=(
            MemoryRecord(
                id=MemoryId("policy-memory"),
                text="Mina said hello before.",
                actor_id=ActorId("actor-policy-runtime"),
            ),
        ),
    )
    llm = FakeLLMClient(responses=("policy-aware reply",))
    app = IrisApp(
        output_pipeline=make_output_pipeline(),
        cycle=wire_core_cognitive_cycle(
            stores=CognitiveCycleStores(
                memory_store=memory_store,
                relationship_store=InMemoryRelationshipStore(),
                affect_store=InMemoryAffectStore(),
            ),
            extension_steps=collect_cognitive_steps(
                [define_chat_feature(wire_response_generator(llm))]
            ),
        ),
    )

    output = await app.process_observation(_actor_message("hello"))
    prompt = llm.requests[0].messages[-1].content

    assert output.text == "policy-aware reply"
    assert "Relevant memories:" in prompt
    assert "Policy constraints: avoid over-familiarity" in prompt
