"""Proactive prompt and generation step tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.cognitive.workspace.frame import (
    AffectSnapshot,
    MemorySummary,
    RelationshipSnapshot,
    WorkspaceFrame,
)
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.memory import MemoryId, MemoryRecord, MemorySearchResult
from iris.contracts.observations import IdleTickObservation, ObservationContext, ObservationKind
from iris.contracts.proactive_talk import (
    ProactiveGenerationOutcome,
    ProactiveGenerationResult,
    ProactiveTalkPrompt,
)
from iris.contracts.workspace_context import ActorContextSnapshot
from iris.core.ids import ActorId, ObservationId, SessionId
from iris.features.proactive_talk.definition import ProactiveActionSelectionStep
from iris.features.proactive_talk.prompts import build_proactive_talk_prompt
from iris.runtime.wiring.cognitive import wire_cognitive_cycle

if TYPE_CHECKING:
    from iris.cognitive.cycle.service import CognitiveCycle


def _frame(idle_seconds: float) -> WorkspaceFrame:
    return WorkspaceFrame(
        observation=IdleTickObservation(
            observation_id=ObservationId("obs-proactive-prompt"),
            session_id=SessionId("session-proactive-prompt"),
            context=ObservationContext(),
            occurred_at=datetime(2026, 7, 18, tzinfo=UTC),
            kind=ObservationKind.IDLE_TICK,
            idle_seconds=idle_seconds,
        ),
        actor_context=ActorContextSnapshot(
            actor=Identity(
                actor_id=ActorId("actor-proactive"),
                actor_kind=ActorKind.HUMAN,
                display_name="Mina",
            )
        ),
        memory_summary=MemorySummary(
            retrieved_memories=(
                MemorySearchResult(
                    record=MemoryRecord(
                        id=MemoryId("memory-proactive"),
                        text="bounded memory summary",
                    ),
                    score=0.9,
                ),
            )
        ),
        affect=AffectSnapshot(affect_summary="calm"),
        relationship=RelationshipSnapshot(relationship_summary="trusted companion"),
    )


@dataclass
class _FakeGenerator:
    result: ProactiveGenerationResult
    calls: int = 0
    prompt: ProactiveTalkPrompt | None = None

    async def generate(self, prompt: ProactiveTalkPrompt) -> ProactiveGenerationResult:
        self.calls += 1
        self.prompt = prompt
        return self.result


def test_prompt_uses_bounded_typed_context_without_transcript() -> None:
    """Proactive prompt は relationship/affect/memory summary だけを使う。"""
    frame = _frame(600.0)

    prompt = build_proactive_talk_prompt(frame)

    assert prompt is not None
    assert prompt.context.actor_display_name == "Mina"
    assert prompt.context.memory_summaries == ("bounded memory summary",)
    assert prompt.context.affect_summary == "calm"
    assert prompt.context.relationship_summary == "trusted companion"
    assert "conversation" not in prompt.model_dump_json()


@pytest.mark.anyio
async def test_salience_denial_skips_generator() -> None:
    """Salience denial は LLM generator を呼ばない。"""
    generator = _FakeGenerator(
        ProactiveGenerationResult(
            outcome=ProactiveGenerationOutcome.GENERATED,
            reason="must not run",
            text="must not send",
        )
    )
    cycle: CognitiveCycle = wire_cognitive_cycle(
        steps=(ProactiveActionSelectionStep(generator=generator),),
    )

    result = await cycle.run(_frame(10.0).observation)

    assert generator.calls == 0
    assert result.selected_plan.is_no_action


@pytest.mark.anyio
async def test_approved_idle_tick_creates_generated_candidate() -> None:
    """Salience approved IdleTick は generated candidate を返す。"""
    generator = _FakeGenerator(
        ProactiveGenerationResult(
            outcome=ProactiveGenerationOutcome.GENERATED,
            reason="generated",
            text="少し休憩しませんか?",
        )
    )
    cycle: CognitiveCycle = wire_cognitive_cycle(
        steps=(ProactiveActionSelectionStep(generator=generator),),
    )

    result = await cycle.run(_frame(600.0).observation)

    assert generator.calls == 1
    assert result.selected_plan.candidate_text == "少し休憩しませんか?"
