"""Event reaction wiring helper."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.event_reaction import (
    EventReactionGenerationResult,
    EventReactionOutcome,
    EventReactionPrompt,
)
from iris.contracts.model_policy import CascadeDecision, ModelCallSite
from iris.contracts.prompting import PromptProfileName
from iris.features.chat.definition import ResponseGenerator, ResponsePrompt
from iris.features.definition import ActivityReactionPromptProvider
from iris.runtime.ingress.event_reaction_decision_pipeline import EventReactionDecisionPipeline
from iris.runtime.observability.logger import LoguruRuntimeLogger
from iris.runtime.wiring.llm import (
    ResponseGeneratorWiringOptions,
    wire_budgeted_response_generator,
    wire_response_generator,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.adapters.llm.ports import LLMClient
    from iris.contracts.retrieval import ContextRetriever
    from iris.features.definition import (
        ActivityReactionPlanner,
        EventReactionGenerator,
        FeatureDefinition,
    )
    from iris.runtime.config.model_call_budget import RuntimeModelCallBudgetConfig
    from iris.runtime.config.prompt_budget import RuntimePromptBudgetConfig
    from iris.runtime.inference.scheduler import LocalInferenceResourceScheduler
    from iris.runtime.observability.ports import RuntimeLogger
    from iris.runtime.persona.prompt_builder import SystemPromptBuilder


_MAX_EVENT_REACTION_CHARS = 600


@dataclass(frozen=True)
class EventReactionResponseGeneratorOptions:
    """Event reaction generatorの境界横断依存を束ねる。"""

    model: str
    temperature: float
    max_tokens: int | None
    prompt_budget_config: RuntimePromptBudgetConfig
    model_call_budget: RuntimeModelCallBudgetConfig
    inference_scheduler: LocalInferenceResourceScheduler | None
    system_prompt_builder: SystemPromptBuilder | None
    context_retriever: ContextRetriever | None = None
    runtime_logger: RuntimeLogger | None = None


def wire_event_reaction_decision_pipeline(
    features: Sequence[FeatureDefinition],
    *,
    generator: EventReactionGenerator | None = None,
    runtime_logger: RuntimeLogger | None = None,
) -> EventReactionDecisionPipeline:
    """FeatureDefinitions から EventReactionDecisionPipeline を組み立てる。

    Args:
        features: 登録されたフィーチャーのリスト。
        generator: 任意のpersona-aware生成器。
        runtime_logger: text-free diagnosticsの出力先。

    Returns:
        EventReactionDecisionPipeline: 配線済みの decision pipeline。
    """
    planners: list[ActivityReactionPlanner] = []
    for feature in features:
        planners.extend(feature.activity_reaction_planners)

    prompt_providers = tuple(
        planner for planner in planners if isinstance(planner, ActivityReactionPromptProvider)
    )
    return EventReactionDecisionPipeline(
        planners=tuple(planners),
        prompt_providers=prompt_providers,
        generator=generator,
        runtime_logger=runtime_logger,
    )


@dataclass(frozen=True)
class EventReactionResponseGenerator:
    """typed event promptをshared response generatorへ渡すruntime adapter。"""

    response_generator: ResponseGenerator
    runtime_logger: RuntimeLogger | None = None

    async def generate(self, prompt: EventReactionPrompt) -> EventReactionGenerationResult:
        """生成結果をevent reaction outcomeへ正規化する。

        Returns:
            EventReactionGenerationResult: 生成・fallback・deferの結果。
        """
        try:
            generated = await self.response_generator.generate_response(
                ResponsePrompt(
                    system_instruction=prompt.instruction,
                    actor_text=_render_event_context(prompt),
                    retrieval_query=prompt.retrieval_query,
                )
            )
        except (OSError, RuntimeError, TimeoutError, ValueError) as error:
            return self._result(
                EventReactionOutcome.DETERMINISTIC_FALLBACK,
                f"generation failed: {type(error).__name__}",
            )

        cascade = generated.cascade_result
        if cascade is not None and cascade.decision is not CascadeDecision.ACCEPT:
            outcome = _outcome_for_cascade(cascade.decision)
            return self._result(outcome, cascade.reason, model=generated.model)
        text = generated.text.strip()
        if not text or len(text) > _MAX_EVENT_REACTION_CHARS:
            return self._result(
                EventReactionOutcome.DETERMINISTIC_FALLBACK,
                "empty or oversized generated text",
                model=generated.model,
            )
        return self._result(
            EventReactionOutcome.GENERATED,
            "generated reaction",
            model=generated.model,
            text=text,
        )

    def _result(
        self,
        outcome: EventReactionOutcome,
        reason: str,
        *,
        model: str | None = None,
        text: str | None = None,
    ) -> EventReactionGenerationResult:
        logger = self.runtime_logger or LoguruRuntimeLogger()
        logger.info(
            "runtime.event_reaction.generation",
            outcome=outcome.value,
            reason=reason,
            model=model,
        )
        return EventReactionGenerationResult(
            outcome=outcome,
            reason=reason,
            model=model,
            text=text,
        )


def wire_event_reaction_response_generator(
    client: LLMClient,
    *,
    options: EventReactionResponseGeneratorOptions,
) -> EventReactionResponseGenerator:
    """Event reaction専用のprompt profile / budget / schedulerを配線する。

    Returns:
        EventReactionResponseGenerator: 配線済みのevent reaction生成器。
    """
    generator = wire_response_generator(
        client,
        options=ResponseGeneratorWiringOptions(
            model=options.model,
            temperature=options.temperature,
            max_tokens=options.max_tokens,
            prompt_budget_config=options.prompt_budget_config,
            prompt_profile=PromptProfileName.PROACTIVE_SHORT,
            call_site=ModelCallSite.EVENT_REACTION,
            model_slot="event_reaction",
            inference_scheduler=options.inference_scheduler,
            system_prompt_builder=options.system_prompt_builder,
            context_retriever=options.context_retriever,
            retrieval_profile=PromptProfileName.PROACTIVE_SHORT,
        ),
    )
    return EventReactionResponseGenerator(
        response_generator=wire_budgeted_response_generator(
            generator,
            options.model_call_budget,
            model=options.model,
            model_slot="event_reaction",
            default_call_site=ModelCallSite.EVENT_REACTION,
            runtime_logger=options.runtime_logger,
        ),
        runtime_logger=options.runtime_logger,
    )


def _render_event_context(prompt: EventReactionPrompt) -> str:
    """Typed contextだけをboundedなprompt文字列へ変換する。

    Returns:
        str: LLMへ渡す正規化済みcontext。
    """
    context = prompt.context
    lines = [
        f"Event kind: {context.activity_kind.value}",
        f"Availability: {context.availability_status.value}",
    ]
    if context.actor_display_name is not None:
        lines.append(f"Actor display name: {context.actor_display_name}")
    if context.presence_status is not None:
        lines.append(f"Presence: {context.presence_status.value}")
    if context.occupant_count is not None:
        lines.append(f"Space occupant count: {context.occupant_count}")
    return "Normalized event context:\n" + "\n".join(lines)


def _outcome_for_cascade(decision: CascadeDecision) -> EventReactionOutcome:
    """Cascade decisionをevent reaction outcomeへ変換する。

    Returns:
        EventReactionOutcome: 安全な後続挙動。
    """
    if decision is CascadeDecision.DEFER:
        return EventReactionOutcome.DEFERRED
    if decision is CascadeDecision.DENY:
        return EventReactionOutcome.NO_SEND
    return EventReactionOutcome.DETERMINISTIC_FALLBACK
