"""ActivityEventObservation の event reaction パイプラインを担当する handler。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from iris.contracts.actions import PresentedOutput

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import SituationContextSnapshot
    from iris.contracts.event_reaction import ReactionCandidate
    from iris.contracts.observations import ActivityEventObservation
    from iris.runtime.ingress.observation_ingress import ObservationIngressContext
    from iris.runtime.ingress.observation_trust import ObservationTrustPolicy
    from iris.runtime.output_pipeline import RuntimeOutputPipeline


class EventReactionDecisionPipelinePort(Protocol):
    """EventReactionDecisionPipeline の runtime 境界 port。"""

    async def decide(
        self,
        observation: ActivityEventObservation,
        *,
        situation_context: SituationContextSnapshot,
    ) -> ReactionCandidate | None:
        """反応条件を満たせばReactionCandidateを返す。"""
        ...


@dataclass(frozen=True)
class ActivityEventReactionHandler:
    """ActivityEventObservation に対する trust check → reaction decision → output pipeline パイプライン。"""

    trust_policy: ObservationTrustPolicy
    decision_pipeline: EventReactionDecisionPipelinePort
    output_pipeline: RuntimeOutputPipeline

    async def handle(
        self,
        observation: ActivityEventObservation,
        situation_context: SituationContextSnapshot | None,
        ingress: ObservationIngressContext,
    ) -> PresentedOutput:
        """Trust check → reaction decision → output pipeline → fallback。

        Args:
            observation: 処理対象の activity event observation。
            situation_context: ランタイムから組み立てられた状況スナップショット。
            ingress: 観測の ingress context。

        Returns:
            PresentedOutput: reaction 出力、または no-send。
        """
        candidate: ReactionCandidate | None = None
        if situation_context is not None and self.trust_policy.can_react_to_activity_event(ingress):
            candidate = await self.decision_pipeline.decide(
                observation,
                situation_context=situation_context,
            )

        if candidate is not None:
            return await self.output_pipeline.present_reaction_candidate(candidate)

        return PresentedOutput(text=None)
