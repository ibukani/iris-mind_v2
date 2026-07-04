"""LLM response generator と inference scheduler の統合テスト。"""

from __future__ import annotations

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.contracts.model_policy import CascadeDecision, CascadeFallbackBehavior, ModelCallSite
from iris.features.chat.definition import ResponsePrompt
from iris.runtime.config.model_call_budget import RuntimeModelCallBudgetConfig
from iris.runtime.inference.models import (
    InferenceLeaseCancellationToken,
    InferenceLeaseRequest,
    InferenceResourceState,
    InferenceSlotKind,
    InferenceWorkPriority,
)
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


async def test_response_generator_does_not_run_background_callback_in_hot_path() -> None:
    """User-facing fallback 中に background cancellation callback を同期実行しない。"""
    scheduler = LocalInferenceResourceScheduler(policy=LocalInferenceResourcePolicy(enabled=True))
    background = await scheduler.acquire(
        InferenceLeaseRequest(
            slot_kind=InferenceSlotKind.BACKGROUND_LLM,
            priority=InferenceWorkPriority.BACKGROUND,
            call_site=ModelCallSite.REFLECTION,
            preemptible=True,
        )
    )
    assert background.lease_id is not None
    token = await scheduler.cancellation_token(background.lease_id)
    assert isinstance(token, InferenceLeaseCancellationToken)
    callback_calls = 0

    def acknowledge_stop() -> None:
        nonlocal callback_calls
        callback_calls += 1
        token.acknowledge_stopped()

    token.register_cancellation_callback(acknowledge_stop)
    client = FakeLLMClient(("ok",), model="fake-local")
    generator = wire_response_generator(
        client,
        options=ResponseGeneratorWiringOptions(
            model="fake-local",
            inference_scheduler=scheduler,
        ),
    )

    first = await generator.generate_response(
        ResponsePrompt(system_instruction="system", actor_text="hello")
    )

    assert len(client.requests) == 0
    assert first.cascade_result is not None
    assert first.cascade_result.reason.startswith("local inference resource defer")
    assert token.cancellation_requested
    assert callback_calls == 0

    assert token.run_cancellation_callbacks() == 1
    second = await generator.generate_response(
        ResponsePrompt(system_instruction="system", actor_text="hello again")
    )

    assert second.model == "fake-local"
    assert len(client.requests) == 1
