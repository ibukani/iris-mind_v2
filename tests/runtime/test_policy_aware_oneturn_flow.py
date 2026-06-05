# Copyright 2025 Iris Mind
"""Tests for policy-aware one-turn cognitive flow with constraints."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.memory.fake import FakeMemoryStore
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.memory import MemoryId, MemoryRecord
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId
from iris.runtime.app import IrisApp
from iris.runtime.wiring.cognitive import (
    wire_policy_affect_memory_aware_text_response_cognitive_cycle,
)


def _actor_message(text: str) -> ActorMessageObservation:
    """Return an ActorMessageObservation with the given text and a test identity."""
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
    """Verify policy-aware flow includes policy constraints in the LLM prompt."""
    memory_store = FakeMemoryStore(
        records=(
            MemoryRecord(
                id=MemoryId("policy-memory"),
                text="Mina said hello before.",
                actor_id=ActorId("actor-policy-runtime"),
            ),
        )
    )
    llm = FakeLLMClient(responses=("policy-aware reply",))
    app = IrisApp(
        cycle=wire_policy_affect_memory_aware_text_response_cognitive_cycle(
            memory_store=memory_store,
            llm_client=llm,
        )
    )

    output = await app.process_observation(_actor_message("hello"))

    prompt = llm.requests[0].messages[-1].content
    assert output.text == "policy-aware reply"
    assert "Relevant memories:" in prompt
    assert "Policy constraints: avoid over-familiarity" in prompt
