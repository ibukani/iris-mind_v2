# Copyright 2025 Iris Mind
"""Tests for memory-aware one-turn cognitive flow."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.memory.fake import FakeMemoryStore
from iris.contracts.memory import MemoryId, MemoryRecord
from iris.contracts.observations import ActorMessageObservation, ObservationKind
from iris.core.ids import ObservationId, SessionId
from iris.runtime.app import IrisApp
from iris.runtime.wiring.cognitive import wire_memory_aware_text_response_cognitive_cycle


def actor_message(text: str = "tea") -> ActorMessageObservation:
    """Return an ActorMessageObservation with the given text."""
    return ActorMessageObservation(
        observation_id=ObservationId("obs-memory-runtime"),
        session_id=SessionId("session-memory-runtime"),
        actor=None,
        space_id=None,
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )


@pytest.mark.anyio
async def test_memory_aware_one_turn_flow_includes_memory_in_llm_prompt() -> None:
    """Verify memory-aware flow includes recalled memories in the LLM prompt."""
    memory_store = FakeMemoryStore(
        records=(MemoryRecord(id=MemoryId("m1"), text="User likes jasmine tea."),)
    )
    llm = FakeLLMClient(responses=("memory-backed reply",))
    app = IrisApp(cycle=wire_memory_aware_text_response_cognitive_cycle(memory_store, llm))

    output = await app.process_observation(actor_message("tea recommendation"))

    assert output.text == "memory-backed reply"
    assert "User likes jasmine tea." in llm.requests[0].messages[-1].content
    assert "tea recommendation" in llm.requests[0].messages[-1].content
