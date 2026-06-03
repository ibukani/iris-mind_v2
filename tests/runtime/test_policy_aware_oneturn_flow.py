from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.memory.fake import FakeMemoryStore
from iris.contracts.identity import Identity
from iris.contracts.memory import MemoryId, MemoryRecord
from iris.contracts.observations import ObservationKind, UserMessageObservation
from iris.core.ids import ExternalRef, ObservationId, SessionId, UserId
from iris.runtime.app import IrisApp
from iris.runtime.wiring.cognitive import wire_policy_affect_memory_aware_text_response_cognitive_cycle


def _user_message(text: str) -> UserMessageObservation:
    return UserMessageObservation(
        observation_id=ObservationId("obs-policy-runtime"),
        session_id=SessionId("session-policy-runtime"),
        actor=Identity(
            user_id=UserId("user-policy-runtime"),
            display_name="Mina",
            provider="test",
            provider_subject=ExternalRef("mina"),
        ),
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.USER_MESSAGE,
        text=text,
    )


@pytest.mark.anyio
async def test_policy_aware_one_turn_flow_includes_policy_context() -> None:
    memory_store = FakeMemoryStore(
        records=(
            MemoryRecord(
                id=MemoryId("policy-memory"),
                text="Mina said hello before.",
                subject_id=UserId("user-policy-runtime"),
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

    output = await app.process_observation(_user_message("hello"))

    prompt = llm.requests[0].messages[-1].content
    assert output.text == "policy-aware reply"
    assert "Relevant memories:" in prompt
    assert "Policy constraints: avoid over-familiarity" in prompt
