"""Runtime model call budget gate tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import override

import pytest

from iris.contracts.model_policy import (
    CascadeDecision,
    CascadeFallbackBehavior,
    CascadeResult,
    ModelCallDescriptor,
    ModelCallKind,
    ModelCallSite,
)
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import ObservationId, SessionId
from iris.features.chat.definition import (
    GeneratedResponse,
    ResponseGenerationStep,
    ResponseGenerator,
    ResponsePrompt,
)
from iris.runtime.app import IrisApp
from iris.runtime.config.model_call_budget import RuntimeModelCallBudgetConfig
from iris.runtime.model_call_budget import ModelCallBudgetGate, bind_model_call_budget_scope
from iris.runtime.observability.context import (
    RuntimeTraceContext,
    bind_trace_context,
    current_trace_counter_snapshot,
)
from iris.runtime.service import IrisRuntimeService, ObservationEnvelope
from iris.runtime.wiring.cognitive import wire_basic_cognitive_cycle, wire_core_cognitive_cycle
from iris.runtime.wiring.llm import BudgetedResponseGenerator
from tests.helpers.output_pipeline import make_output_pipeline


def test_large_llm_budget_allows_one_user_response_call_and_avoids_second() -> None:
    """user-facing hot path では large LLM 2 回目を fallback として回避する。"""
    gate = ModelCallBudgetGate(RuntimeModelCallBudgetConfig())
    descriptor = _descriptor()

    with bind_trace_context(_trace_context()), bind_model_call_budget_scope():
        first = gate.check_and_record(descriptor)
        second = gate.check_and_record(descriptor)
        snapshot = current_trace_counter_snapshot()

    assert first.decision is CascadeDecision.ACCEPT
    assert second.decision is CascadeDecision.FALLBACK
    assert second.fallback_behavior is CascadeFallbackBehavior.DETERMINISTIC_BASELINE
    assert snapshot.avoided_large_llm_call_count == 1


def test_low_confidence_falls_back_with_reason_and_model_metadata() -> None:
    """低信頼度では fallback behavior と model metadata を返す。"""
    gate = ModelCallBudgetGate(RuntimeModelCallBudgetConfig())
    descriptor = _descriptor(confidence=0.2)

    with bind_model_call_budget_scope():
        result = gate.check_and_record(descriptor)

    assert result.decision is CascadeDecision.FALLBACK
    assert result.reason == "low confidence fallback"
    assert abs(result.confidence - 0.2) < 1e-9
    assert result.fallback_behavior is CascadeFallbackBehavior.DETERMINISTIC_BASELINE
    assert result.model_metadata["model_slot"] == "default_chat"


def test_low_confidence_high_risk_can_escalate_when_policy_allows_it() -> None:
    """high-risk / uncertain のときだけ上位モデル escalation を許可できる。"""
    gate = ModelCallBudgetGate(RuntimeModelCallBudgetConfig())
    descriptor = _descriptor(confidence=0.2, high_risk=True)

    with bind_model_call_budget_scope():
        result = gate.check_and_record(descriptor)

    assert result.decision is CascadeDecision.ESCALATE
    assert result.reason == "low confidence allows escalation"
    assert result.fallback_behavior is None


@pytest.mark.anyio
async def test_budgeted_response_generator_executes_deterministic_fallback_after_budget() -> None:
    """BudgetedResponseGenerator は budget 超過時に deterministic fallback を実行する。"""
    wrapped = _CountingResponseGenerator()
    generator = BudgetedResponseGenerator(
        wrapped,
        ModelCallBudgetGate(RuntimeModelCallBudgetConfig()),
        model_name="fake-llm",
        model_slot="default_chat",
    )
    prompt = ResponsePrompt(system_instruction="system", actor_text="hello")

    with bind_model_call_budget_scope():
        first = await generator.generate_response(prompt)
        second = await generator.generate_response(prompt)

    assert first.text == "reply-1"
    assert first.cascade_result is not None
    assert first.cascade_result.decision is CascadeDecision.ACCEPT
    assert second.text == "受け取りました。必要なら、もう少し詳しく教えてください。"
    assert second.model == "fake-llm:deterministic_baseline"
    assert second.cascade_result is not None
    assert second.cascade_result.decision is CascadeDecision.FALLBACK
    assert second.cascade_result.fallback_behavior is CascadeFallbackBehavior.DETERMINISTIC_BASELINE
    assert wrapped.calls == 1


@pytest.mark.anyio
async def test_budgeted_response_generator_normalizes_unwired_escalation_to_defer() -> None:
    """上位モデル配線がない escalation は暗黙再呼び出しせず defer に正規化する。"""
    wrapped = _CountingResponseGenerator()
    generator = BudgetedResponseGenerator(
        wrapped,
        _EscalatingGate(),
        model_name="fake-llm",
        model_slot="default_chat",
    )

    response = await generator.generate_response(
        ResponsePrompt(system_instruction="system", actor_text="hello")
    )

    assert not response.text
    assert response.cascade_result is not None
    assert response.cascade_result.decision is CascadeDecision.DEFER
    assert response.cascade_result.fallback_behavior is CascadeFallbackBehavior.DEFER
    assert wrapped.calls == 0


@pytest.mark.anyio
async def test_response_generation_step_uses_deterministic_fallback_text() -> None:
    """Deterministic fallback は no-action ではなく候補応答として扱う。"""
    cycle = wire_basic_cognitive_cycle(
        extension_steps=(ResponseGenerationStep(_FallbackResponseGenerator()),)
    )

    result = await cycle.run(_actor_message("hello"))

    assert result.selected_plan.should_respond is True
    assert result.selected_plan.candidate_text == "fallback reply"


@pytest.mark.anyio
async def test_runtime_service_user_response_hot_path_shares_one_request_budget() -> None:
    """1つの user-facing turn 内では複数 response step で large LLM budget を共有する。"""
    first_generator = _CountingResponseGenerator(prefix="first")
    second_generator = _CountingResponseGenerator(prefix="second")
    gate = ModelCallBudgetGate(RuntimeModelCallBudgetConfig())
    app = IrisApp(
        output_pipeline=make_output_pipeline(),
        cycle=wire_core_cognitive_cycle(
            extension_steps=(
                ResponseGenerationStep(
                    BudgetedResponseGenerator(
                        first_generator,
                        gate,
                        model_name="fake-llm",
                        model_slot="default_chat",
                    ),
                    priority=10,
                ),
                ResponseGenerationStep(
                    BudgetedResponseGenerator(
                        second_generator,
                        gate,
                        model_name="fake-llm",
                        model_slot="default_chat",
                    ),
                    priority=1,
                ),
            )
        ),
    )
    service = IrisRuntimeService(app)

    response = await service.handle_observation(
        ObservationEnvelope.external_client(observation=_actor_message("hello"))
    )

    assert response.output.text == "first-1"
    assert first_generator.calls == 1
    assert second_generator.calls == 0


class _FallbackResponseGenerator(ResponseGenerator):
    """deterministic fallback 済みの応答を返す ResponseGenerator stub。"""

    @override
    async def generate_response(self, prompt: ResponsePrompt) -> GeneratedResponse:
        """Fallback 応答を返す。

        Returns:
            GeneratedResponse: fallback cascade result 付きの応答。
        """
        _ = prompt
        return GeneratedResponse(
            text="fallback reply",
            model="fake-llm:deterministic_baseline",
            cascade_result=CascadeResult(
                decision=CascadeDecision.FALLBACK,
                reason="model call budget exceeded",
                confidence=1.0,
                fallback_behavior=CascadeFallbackBehavior.DETERMINISTIC_BASELINE,
                model_metadata={"model_slot": "default_chat", "model": "fake-llm"},
            ),
        )


class _EscalatingGate(ModelCallBudgetGate):
    """常に escalation を返す gate stub。"""

    @override
    def check_and_record(self, descriptor: ModelCallDescriptor) -> CascadeResult:
        """上位モデル escalation 判定を返す。

        Returns:
            CascadeResult: escalation 判定。
        """
        return CascadeResult(
            decision=CascadeDecision.ESCALATE,
            reason="low confidence allows escalation",
            confidence=0.2,
            fallback_behavior=None,
            model_metadata=descriptor.metadata,
        )


class _CountingResponseGenerator(ResponseGenerator):
    """呼び出し回数を数える ResponseGenerator stub。"""

    def __init__(self, *, prefix: str = "reply") -> None:
        self.calls = 0
        self._prefix = prefix

    @override
    async def generate_response(self, prompt: ResponsePrompt) -> GeneratedResponse:
        """呼び出し回数入りの応答を返す。

        Returns:
            GeneratedResponse: 呼び出し回数を含む stub 応答。
        """
        _ = prompt
        self.calls += 1
        return GeneratedResponse(text=f"{self._prefix}-{self.calls}", model="fake-llm")


def _descriptor(
    *,
    confidence: float = 1.0,
    high_risk: bool = False,
) -> ModelCallDescriptor:
    return ModelCallDescriptor(
        call_kind=ModelCallKind.LARGE_LLM,
        call_site=ModelCallSite.USER_RESPONSE_HOT_PATH,
        model_slot="default_chat",
        model_name="fake-llm",
        confidence=confidence,
        high_risk=high_risk,
        metadata={"model_slot": "default_chat", "model": "fake-llm"},
    )


def _trace_context() -> RuntimeTraceContext:
    return RuntimeTraceContext(
        correlation_id="corr-model-budget",
        observation_id="obs-model-budget",
        observation_kind="actor_message",
        ingress_kind="external_client",
        adapter_id=None,
        provider=None,
        actor_id="actor-model-budget",
        space_id=None,
    )


def _actor_message(text: str) -> ActorMessageObservation:
    return ActorMessageObservation(
        observation_id=ObservationId("obs-model-budget-flow"),
        session_id=SessionId("session-model-budget-flow"),
        context=ObservationContext(),
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )
