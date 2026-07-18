"""Proactive text generator wiring tests."""

from __future__ import annotations

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.contracts.proactive_talk import (
    ProactiveGenerationOutcome,
    ProactiveTalkContext,
    ProactiveTalkPrompt,
)
from iris.runtime.config.model_call_budget import RuntimeModelCallBudgetConfig
from iris.runtime.config.prompt_budget import RuntimePromptBudgetConfig
from iris.runtime.inference.models import InferenceResourceState
from iris.runtime.inference.policy import LocalInferenceResourcePolicy
from iris.runtime.inference.scheduler import LocalInferenceResourceScheduler
from iris.runtime.wiring.proactive_talk import (
    ProactiveTextResponseGenerator,
    ProactiveTextResponseGeneratorOptions,
    wire_proactive_text_response_generator,
)

pytestmark = pytest.mark.anyio

_PROMPT = ProactiveTalkPrompt(
    context=ProactiveTalkContext(
        idle_seconds=600.0,
        actor_display_name="Mina",
        memory_summaries=("bounded memory",),
    ),
    instruction="Write one short proactive message.",
)


def _generator(
    client: FakeLLMClient,
    *,
    scheduler: LocalInferenceResourceScheduler | None = None,
) -> ProactiveTextResponseGenerator:
    return wire_proactive_text_response_generator(
        client,
        options=ProactiveTextResponseGeneratorOptions(
            model="fake-local",
            temperature=0.0,
            max_tokens=40,
            prompt_budget_config=RuntimePromptBudgetConfig(),
            model_call_budget=RuntimeModelCallBudgetConfig(),
            inference_scheduler=scheduler,
            system_prompt_builder=None,
        ),
    )


async def test_proactive_generator_uses_short_profile_and_call_context() -> None:
    """Proactive generator は bounded context を short prompt に渡す。"""
    client = FakeLLMClient(("短い proactive message",), model="fake-local")

    result = await _generator(client).generate(_PROMPT)

    assert result.outcome is ProactiveGenerationOutcome.GENERATED
    assert result.text == "短い proactive message"
    assert len(client.requests) == 1
    assert "Normalized proactive context:" in client.requests[0].messages[-1].content
    assert "bounded memory" in client.requests[0].messages[-1].content


async def test_proactive_generator_busy_does_not_call_model() -> None:
    """推論資源 busy 時は blocking wait せず no-send にする。"""
    scheduler = LocalInferenceResourceScheduler(policy=LocalInferenceResourcePolicy(enabled=True))
    await scheduler.set_state(InferenceResourceState.BUSY)
    client = FakeLLMClient(("must not be used",), model="fake-local")

    result = await _generator(client, scheduler=scheduler).generate(_PROMPT)

    assert result.outcome is ProactiveGenerationOutcome.NO_SEND
    assert client.requests == ()


async def test_proactive_generator_unavailable_does_not_call_model() -> None:
    """推論資源 unavailable 時は no-send にする。"""
    scheduler = LocalInferenceResourceScheduler(policy=LocalInferenceResourcePolicy(enabled=True))
    await scheduler.set_state(InferenceResourceState.UNAVAILABLE)
    client = FakeLLMClient(("must not be used",), model="fake-local")

    result = await _generator(client, scheduler=scheduler).generate(_PROMPT)

    assert result.outcome is ProactiveGenerationOutcome.NO_SEND
    assert client.requests == ()
