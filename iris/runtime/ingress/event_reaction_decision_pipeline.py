"""イベント反応（event reaction）の決定パイプライン。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.actions import ActionPlan
from iris.contracts.event_reaction import EventReactionOutcome
from iris.runtime.observability.logger import LoguruRuntimeLogger

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.contracts.observations import ActivityEventObservation
    from iris.contracts.workspace_context import SituationContextSnapshot
    from iris.features.definition import (
        ActivityReactionPlanner,
        ActivityReactionPromptProvider,
        EventReactionGenerator,
    )
    from iris.runtime.observability.ports import RuntimeLogger


@dataclass(frozen=True)
class EventReactionDecisionPipeline:
    """ActivityEventObservationに対してfallback付き反応を計画する。"""

    planners: Sequence[ActivityReactionPlanner]
    prompt_providers: Sequence[ActivityReactionPromptProvider] = ()
    generator: EventReactionGenerator | None = None
    runtime_logger: RuntimeLogger | None = None

    async def decide(
        self,
        observation: ActivityEventObservation,
        *,
        situation_context: SituationContextSnapshot,
    ) -> ActionPlan | None:
        """プランナーを順に実行し、ActionPlanを返す。

        Args:
            observation: 処理対象の観測。
            situation_context: ランタイムから組み立てられた状況スナップショット。

        Returns:
            ActionPlan | None: 反応候補があればそれ、なければNone。
        """
        for planner in self.planners:
            decision = planner.plan(
                observation,
                availability=situation_context.availability,
            )
            if decision.should_react and decision.candidate is not None:
                return await self._resolve_candidate(
                    decision.candidate,
                    observation,
                    situation_context,
                )
            self._log_outcome(
                observation.activity_kind.value,
                EventReactionOutcome.NO_SEND,
                decision.reason,
            )

        return None

    async def _resolve_candidate(
        self,
        candidate: ActionPlan,
        observation: ActivityEventObservation,
        situation_context: SituationContextSnapshot,
    ) -> ActionPlan | None:
        provider = self._provider_for_prompt(observation, situation_context)
        resolved_candidate: ActionPlan | None = candidate
        if self.generator is None or provider is None:
            self._log_outcome(
                observation.activity_kind.value,
                EventReactionOutcome.DETERMINISTIC_FALLBACK,
                "generation disabled",
            )
        else:
            prompt = provider.build_prompt(
                observation,
                situation_context=situation_context,
            )
            if prompt is None:
                self._log_outcome(
                    observation.activity_kind.value,
                    EventReactionOutcome.DETERMINISTIC_FALLBACK,
                    "prompt unavailable",
                )
            else:
                result = await self.generator.generate(prompt)
                self._log_outcome(
                    observation.activity_kind.value,
                    result.outcome,
                    result.reason,
                )
                if result.outcome is EventReactionOutcome.GENERATED and result.text:
                    resolved_candidate = ActionPlan(
                        turn_intent=candidate.turn_intent,
                        candidate_text=result.text,
                        should_respond=candidate.should_respond,
                        priority=candidate.priority,
                        interruptible=candidate.interruptible,
                        delay_ms=candidate.delay_ms,
                    )
                elif result.outcome in {
                    EventReactionOutcome.NO_SEND,
                    EventReactionOutcome.DEFERRED,
                }:
                    resolved_candidate = None
        return resolved_candidate

    def _provider_for_prompt(
        self,
        observation: ActivityEventObservation,
        situation_context: SituationContextSnapshot,
    ) -> ActivityReactionPromptProvider | None:
        for provider in self.prompt_providers:
            if provider.build_prompt(observation, situation_context=situation_context) is not None:
                return provider
        return None

    def _log_outcome(
        self,
        activity_kind: str,
        outcome: EventReactionOutcome,
        reason: str,
    ) -> None:
        logger = self.runtime_logger or LoguruRuntimeLogger()
        logger.info(
            "runtime.event_reaction.decision",
            activity_kind=activity_kind,
            outcome=outcome.value,
            reason=reason,
        )
