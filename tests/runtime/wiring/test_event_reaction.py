"""Event reaction generation wiring tests。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.contracts.activity import ActivityKind
from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.contracts.event_reaction import (
    EventReactionGenerationResult,
    EventReactionOutcome,
    EventReactionPrompt,
)
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActivityEventObservation,
    ObservationContext,
    ObservationKind,
)
from iris.contracts.workspace_context import SituationContextSnapshot
from iris.core.ids import ActorId, ObservationId, SessionId
from iris.features.event_reaction.definition import define_event_reaction_feature
from iris.features.event_reaction.planner import EventReactionPlanner
from iris.features.event_reaction.policy import default_event_reaction_policy
from iris.features.event_reaction.templates import EventReactionTemplateProvider
from iris.runtime.config.model_call_budget import RuntimeModelCallBudgetConfig
from iris.runtime.config.prompt_budget import RuntimePromptBudgetConfig
from iris.runtime.inference.models import InferenceLeaseDecision, InferenceResourceState
from iris.runtime.inference.policy import LocalInferenceResourcePolicy
from iris.runtime.inference.scheduler import LocalInferenceResourceScheduler
from iris.runtime.ingress.event_reaction_decision_pipeline import EventReactionDecisionPipeline
from iris.runtime.wiring.event_reaction import (
    EventReactionResponseGeneratorOptions,
    wire_event_reaction_decision_pipeline,
    wire_event_reaction_response_generator,
)

pytestmark = pytest.mark.anyio

_NOW = datetime(2026, 7, 18, tzinfo=UTC)


@dataclass(frozen=True)
class _FakeReactionGenerator:
    result: EventReactionGenerationResult

    async def generate(self, prompt: EventReactionPrompt) -> EventReactionGenerationResult:
        del prompt
        return self.result


def _observation(kind: ActivityKind = ActivityKind.VOICE_JOINED) -> ActivityEventObservation:
    return ActivityEventObservation(
        observation_id=ObservationId("observation-1"),
        session_id=SessionId("session-1"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-1"),
                actor_kind=ActorKind.HUMAN,
                display_name="Mina",
            ),
            source="test",
        ),
        occurred_at=_NOW,
        kind=ObservationKind.ACTIVITY_EVENT,
        activity_kind=kind,
    )


def _situation() -> SituationContextSnapshot:
    return SituationContextSnapshot(
        availability=AvailabilitySnapshot(
            actor_id=ActorId("actor-1"),
            status=AvailabilityStatus.AVAILABLE,
            reason="test",
            observed_at=_NOW,
            computed_at=_NOW,
        )
    )


def _prompt() -> EventReactionPrompt:
    prompt = EventReactionPlanner(
        policy=default_event_reaction_policy(),
        template_provider=EventReactionTemplateProvider(),
    ).build_prompt(
        _observation(),
        situation_context=_situation(),
    )
    assert prompt is not None
    return prompt


async def test_pipeline_replaces_deterministic_candidate_with_generated_text() -> None:
    """生成成功時だけdeterministic candidateをbounded textで置き換える。"""
    pipeline = wire_event_reaction_decision_pipeline(
        (define_event_reaction_feature(),),
        generator=_FakeReactionGenerator(
            EventReactionGenerationResult(
                outcome=EventReactionOutcome.GENERATED,
                reason="test generated",
                model="fake-local",
                text="Welcome, Mina.",
            )
        ),
    )

    candidate = await pipeline.decide(_observation(), situation_context=_situation())

    assert candidate is not None
    assert candidate.candidate_text == "Welcome, Mina."


async def test_pipeline_returns_no_send_for_deferred_generation() -> None:
    """Defer / no-send結果はfallback候補を配送しない。"""
    pipeline = EventReactionDecisionPipeline(
        planners=wire_event_reaction_decision_pipeline((define_event_reaction_feature(),)).planners,
        prompt_providers=wire_event_reaction_decision_pipeline(
            (define_event_reaction_feature(),)
        ).prompt_providers,
        generator=_FakeReactionGenerator(
            EventReactionGenerationResult(
                outcome=EventReactionOutcome.DEFERRED,
                reason="scheduler busy",
            )
        ),
    )

    candidate = await pipeline.decide(_observation(), situation_context=_situation())

    assert candidate is None


async def test_response_generator_uses_short_prompt_and_generates_text() -> None:
    """Event reactionはshared assemblerのshort profileを使う。"""
    client = FakeLLMClient(("Persona-aware greeting",), model="fake-local")
    generator = wire_event_reaction_response_generator(
        client,
        options=EventReactionResponseGeneratorOptions(
            model="fake-local",
            temperature=0.0,
            max_tokens=40,
            prompt_budget_config=RuntimePromptBudgetConfig(),
            model_call_budget=RuntimeModelCallBudgetConfig(),
            inference_scheduler=None,
            system_prompt_builder=None,
        ),
    )

    result = await generator.generate(_prompt())

    assert result.outcome is EventReactionOutcome.GENERATED
    assert result.text == "Persona-aware greeting"
    assert len(client.requests) == 1
    assert "Event kind: voice_joined" in client.requests[0].messages[-1].content


async def test_response_generator_busy_scheduler_returns_no_send() -> None:
    """Scheduler busy時はblocking waitせずno-sendになる。"""
    scheduler = LocalInferenceResourceScheduler(policy=LocalInferenceResourcePolicy(enabled=True))
    await scheduler.set_state(InferenceResourceState.BUSY)
    client = FakeLLMClient(("must not be used",), model="fake-local")
    generator = wire_event_reaction_response_generator(
        client,
        options=EventReactionResponseGeneratorOptions(
            model="fake-local",
            temperature=0.0,
            max_tokens=40,
            prompt_budget_config=RuntimePromptBudgetConfig(),
            model_call_budget=RuntimeModelCallBudgetConfig(),
            inference_scheduler=scheduler,
            system_prompt_builder=None,
        ),
    )

    result = await generator.generate(_prompt())

    assert result.outcome is EventReactionOutcome.NO_SEND
    assert client.requests == ()


async def test_response_generator_unavailable_keeps_deterministic_fallback() -> None:
    """Scheduler unavailable時はLLMを呼ばずfallback結果を返す。"""
    scheduler = LocalInferenceResourceScheduler(
        policy=LocalInferenceResourcePolicy(
            enabled=True,
            proactive_when_unavailable=InferenceLeaseDecision.DENIED,
        )
    )
    await scheduler.set_state(InferenceResourceState.UNAVAILABLE)
    client = FakeLLMClient(("must not be used",), model="fake-local")
    generator = wire_event_reaction_response_generator(
        client,
        options=EventReactionResponseGeneratorOptions(
            model="fake-local",
            temperature=0.0,
            max_tokens=40,
            prompt_budget_config=RuntimePromptBudgetConfig(),
            model_call_budget=RuntimeModelCallBudgetConfig(),
            inference_scheduler=scheduler,
            system_prompt_builder=None,
        ),
    )

    result = await generator.generate(_prompt())

    assert result.outcome is EventReactionOutcome.DETERMINISTIC_FALLBACK
    assert client.requests == ()
