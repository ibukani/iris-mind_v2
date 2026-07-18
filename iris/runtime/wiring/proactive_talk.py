"""Proactive text generation runtime adapter and wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.model_policy import (
    CascadeDecision,
    CascadeFallbackBehavior,
    ModelCallSite,
)
from iris.contracts.proactive_talk import (
    ProactiveGenerationOutcome,
    ProactiveGenerationResult,
    ProactiveTalkPrompt,
)
from iris.contracts.prompting import PromptProfileName
from iris.features.chat.definition import ResponseGenerator, ResponsePrompt
from iris.runtime.observability.logger import LoguruRuntimeLogger
from iris.runtime.wiring.llm import (
    ResponseGeneratorWiringOptions,
    wire_budgeted_response_generator,
    wire_response_generator,
)

if TYPE_CHECKING:
    from iris.adapters.llm.ports import LLMClient
    from iris.contracts.retrieval import ContextRetriever
    from iris.runtime.config.model_call_budget import RuntimeModelCallBudgetConfig
    from iris.runtime.config.prompt_budget import RuntimePromptBudgetConfig
    from iris.runtime.inference.scheduler import LocalInferenceResourceScheduler
    from iris.runtime.observability.ports import RuntimeLogger
    from iris.runtime.persona.prompt_builder import SystemPromptBuilder


_MAX_PROACTIVE_TEXT_CHARS = 600


@dataclass(frozen=True)
class ProactiveTextResponseGeneratorOptions:
    """Proactive generator の境界横断依存を束ねる。"""

    model: str
    temperature: float
    max_tokens: int | None
    prompt_budget_config: RuntimePromptBudgetConfig
    model_call_budget: RuntimeModelCallBudgetConfig
    inference_scheduler: LocalInferenceResourceScheduler | None
    system_prompt_builder: SystemPromptBuilder | None
    context_retriever: ContextRetriever | None = None
    runtime_logger: RuntimeLogger | None = None


@dataclass(frozen=True)
class ProactiveTextResponseGenerator:
    """Typed proactive prompt を shared response generator へ渡す adapter。"""

    response_generator: ResponseGenerator
    runtime_logger: RuntimeLogger | None = None

    async def generate(self, prompt: ProactiveTalkPrompt) -> ProactiveGenerationResult:
        """生成結果を proactive outcome へ正規化する。

        Returns:
            bounded な proactive generation result。
        """
        try:
            generated = await self.response_generator.generate_response(
                ResponsePrompt(
                    system_instruction=prompt.instruction,
                    actor_text=_render_proactive_context(prompt),
                    memory_snippets=prompt.context.memory_summaries,
                    affect_context=prompt.context.affect_summary,
                    relationship_context=prompt.context.relationship_summary,
                    constraints=prompt.context.policy_instructions,
                    retrieval_query=prompt.retrieval_query,
                )
            )
        except (OSError, RuntimeError, TimeoutError, ValueError) as error:
            return self._result(
                ProactiveGenerationOutcome.NO_SEND,
                f"generation failed: {type(error).__name__}",
            )

        cascade = generated.cascade_result
        if cascade is not None and cascade.decision is not CascadeDecision.ACCEPT:
            return self._result(
                _outcome_for_cascade(cascade.decision, cascade.fallback_behavior),
                cascade.reason,
                model=generated.model,
            )
        text = generated.text.strip()
        if not text or len(text) > _MAX_PROACTIVE_TEXT_CHARS:
            return self._result(
                ProactiveGenerationOutcome.NO_SEND,
                "empty or oversized generated text",
                model=generated.model,
            )
        return self._result(
            ProactiveGenerationOutcome.GENERATED,
            "generated proactive text",
            model=generated.model,
            text=text,
        )

    def _result(
        self,
        outcome: ProactiveGenerationOutcome,
        reason: str,
        *,
        model: str | None = None,
        text: str | None = None,
    ) -> ProactiveGenerationResult:
        """Text-free outcome を記録して typed result を返す。

        Returns:
            記録対象の proactive generation result。
        """
        logger = self.runtime_logger or LoguruRuntimeLogger()
        logger.info(
            "runtime.proactive.generation",
            outcome=outcome.value,
            reason=reason,
            model=model,
        )
        return ProactiveGenerationResult(
            outcome=outcome,
            reason=reason,
            model=model,
            text=text,
        )


def wire_proactive_text_response_generator(
    client: LLMClient,
    *,
    options: ProactiveTextResponseGeneratorOptions,
) -> ProactiveTextResponseGenerator:
    """proactive_short / PROACTIVE の generator を組み立てる。

    Returns:
        配線済みの proactive text generator。
    """
    generator = wire_response_generator(
        client,
        options=ResponseGeneratorWiringOptions(
            model=options.model,
            temperature=options.temperature,
            max_tokens=options.max_tokens,
            prompt_budget_config=options.prompt_budget_config,
            prompt_profile=PromptProfileName.PROACTIVE_SHORT,
            call_site=ModelCallSite.PROACTIVE,
            model_slot="proactive_talk",
            inference_scheduler=options.inference_scheduler,
            system_prompt_builder=options.system_prompt_builder,
            context_retriever=options.context_retriever,
            retrieval_profile=PromptProfileName.PROACTIVE_SHORT,
        ),
    )
    return ProactiveTextResponseGenerator(
        response_generator=wire_budgeted_response_generator(
            generator,
            options.model_call_budget,
            model=options.model,
            model_slot="proactive_talk",
            default_call_site=ModelCallSite.PROACTIVE,
            runtime_logger=options.runtime_logger,
        ),
        runtime_logger=options.runtime_logger,
    )


def _render_proactive_context(prompt: ProactiveTalkPrompt) -> str:
    """Typed context だけを bounded な user message へ変換する。

    Returns:
        正規化済み context 文字列。
    """
    context = prompt.context
    lines = [
        f"Idle seconds: {context.idle_seconds:.1f}",
        f"Availability: {context.availability_status.value}",
    ]
    if context.actor_display_name is not None:
        lines.append(f"Actor display name: {context.actor_display_name}")
    if context.presence_status is not None:
        lines.append(f"Presence: {context.presence_status.value}")
    if context.occupant_count is not None:
        lines.append(f"Space occupant count: {context.occupant_count}")
    if context.affect_summary is not None:
        lines.append(f"Affect summary: {context.affect_summary}")
    if context.relationship_summary is not None:
        lines.append(f"Relationship summary: {context.relationship_summary}")
    lines.extend(f"Memory summary: {value}" for value in context.memory_summaries)
    lines.extend(f"Policy instruction: {value}" for value in context.policy_instructions)
    return "Normalized proactive context:\n" + "\n".join(lines)


def _outcome_for_cascade(
    decision: CascadeDecision,
    fallback_behavior: CascadeFallbackBehavior | None = None,
) -> ProactiveGenerationOutcome:
    """Cascade decision を proactive outcome へ変換する。

    Returns:
        安全な proactive generation outcome。
    """
    if decision is CascadeDecision.DEFER:
        return ProactiveGenerationOutcome.DEFERRED
    if decision is CascadeDecision.DENY:
        if fallback_behavior is CascadeFallbackBehavior.NO_OP:
            return ProactiveGenerationOutcome.NO_SEND
        return ProactiveGenerationOutcome.BLOCKED
    return ProactiveGenerationOutcome.NO_SEND
