"""LLM response generator と inference scheduler の統合テスト。"""

from __future__ import annotations

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.contracts.model_policy import CascadeDecision, CascadeFallbackBehavior
from iris.features.chat.definition import ResponsePrompt
from iris.runtime.config.model_call_budget import RuntimeModelCallBudgetConfig
from iris.runtime.inference.models import InferenceResourceState
from iris.runtime.inference.policy import LocalInferenceResourcePolicy
from iris.runtime.inference.scheduler import LocalInferenceResourceScheduler
from iris.runtime.model_call_budget import ModelCallBudgetGate, bind_model_call_budget_scope
from iris.runtime.wiring.llm import (
    BudgetedResponseGenerator,
    ResponseGeneratorWiringOptions,
    wire_response_generator,
)

pytestmark = pytest.mark.anyio


async def test_response_generator_does_not_call_llm_when_resource_unavailable() -> None:
    """Unavailable 時は provider を呼ばず deterministic fallback を返す。"""
    scheduler = LocalInferenceResourceScheduler(policy=LocalInferenceResourcePolicy(enabled=True))
    await scheduler.set_state(InferenceResourceState.UNAVAILABLE)
    client = FakeLLMClient(("should not be used",))
    generator = wire_response_generator(
        client,
        options=ResponseGeneratorWiringOptions(
            model="fake-local",
            inference_scheduler=scheduler,
        ),
    )

    response = await generator.generate_response(
        ResponsePrompt(system_instruction="system", actor_text="hello")
    )

    assert client.requests == ()
    assert response.text == "受け取りました。必要なら、もう少し詳しく教えてください。"
    assert response.model == "fake-local:inference_scheduler_baseline"
    assert response.cascade_result is not None
    assert response.cascade_result.decision is CascadeDecision.FALLBACK
    assert (
        response.cascade_result.fallback_behavior is CascadeFallbackBehavior.DETERMINISTIC_BASELINE
    )


async def test_response_generator_releases_lease_after_success() -> None:
    """Provider 呼び出し後は large LLM lease を解放する。"""
    scheduler = LocalInferenceResourceScheduler(policy=LocalInferenceResourcePolicy(enabled=True))
    client = FakeLLMClient(("ok",), model="fake-local")
    generator = wire_response_generator(
        client,
        options=ResponseGeneratorWiringOptions(
            model="fake-local",
            inference_scheduler=scheduler,
        ),
    )

    response = await generator.generate_response(
        ResponsePrompt(system_instruction="system", actor_text="hello")
    )

    assert response.text == "ok"
    assert len(client.requests) == 1
    snapshot = await scheduler.snapshot()
    assert snapshot.active_large_slots == 0


async def test_budgeted_response_generator_preserves_scheduler_fallback() -> None:
    """Budget wrapper は scheduler 側の deny/defer cascade を accept で上書きしない。"""
    scheduler = LocalInferenceResourceScheduler(policy=LocalInferenceResourcePolicy(enabled=True))
    await scheduler.set_state(InferenceResourceState.UNAVAILABLE)
    inner = wire_response_generator(
        FakeLLMClient(("should not be used",)),
        options=ResponseGeneratorWiringOptions(
            model="fake-local",
            inference_scheduler=scheduler,
        ),
    )
    generator = BudgetedResponseGenerator(
        inner,
        ModelCallBudgetGate(RuntimeModelCallBudgetConfig()),
        model_name="fake-local",
        model_slot="default_chat",
    )

    with bind_model_call_budget_scope():
        response = await generator.generate_response(
            ResponsePrompt(system_instruction="system", actor_text="hello")
        )

    assert response.cascade_result is not None
    assert response.cascade_result.decision is CascadeDecision.FALLBACK
    assert response.cascade_result.reason.startswith("local inference resource denied")
