from __future__ import annotations

from typing import cast

from iris.cognitive.cycle.models import ActionSelectionResult, PolicyResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.features.definition import FeatureDefinition
from iris.features.proactive_talk.goals import GoalProposer, action_plan_from_goal
from iris.features.proactive_talk.models import ProactiveFrameContext
from iris.features.proactive_talk.policy import (
    policy_summary,
    proactive_action_preferences,
    proactive_policy_constraints,
)
from iris.features.proactive_talk.scoring import SalienceScorer


class ProactivePolicyStep(PipelineStep[PolicyResult]):
    name = "proactive_policy"

    async def run(self, frame: object) -> PolicyResult:
        proactive_frame = cast(ProactiveFrameContext, frame)
        constraints = proactive_policy_constraints(proactive_frame)
        preferences = proactive_action_preferences(constraints)
        all_constraints = proactive_frame.constraints + constraints
        return PolicyResult(
            step_name=self.name,
            status=StepStatus.OK,
            constraints=all_constraints,
            action_preferences=proactive_frame.action_preferences + preferences,
            response_allowed=not any(constraint.blocks_response for constraint in all_constraints),
            policy_summary=policy_summary(all_constraints),
        )


class ProactiveActionSelectionStep(PipelineStep[ActionSelectionResult]):
    name = "proactive_action_selection"

    def __init__(
        self,
        scorer: SalienceScorer | None = None,
        proposer: GoalProposer | None = None,
    ) -> None:
        self._scorer = scorer or SalienceScorer()
        self._proposer = proposer or GoalProposer()

    async def run(self, frame: object) -> ActionSelectionResult:
        proactive_frame = cast(ProactiveFrameContext, frame)
        salience = self._scorer.score(proactive_frame)
        goal = self._proposer.propose(salience)
        plan = action_plan_from_goal(goal)
        return ActionSelectionResult(
            step_name=self.name,
            status=StepStatus.OK,
            action_plans=(plan,),
        )


def define_proactive_talk_feature(salience_threshold: float = 0.5) -> FeatureDefinition:
    scorer = SalienceScorer(threshold=salience_threshold)
    return FeatureDefinition(
        name="proactive_talk",
        pipeline_steps=(
            ProactivePolicyStep(),
            ProactiveActionSelectionStep(scorer=scorer, proposer=GoalProposer()),
        ),
    )
