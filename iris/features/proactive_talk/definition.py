"""プロアクティブ発話機能のパイプラインステップとファクトリ。"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from loguru import logger

from iris.cognitive.cycle.models import ActionSelectionResult, PolicyResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.contracts.actions import ActionPlan
from iris.contracts.proactive_talk import ProactiveGenerationOutcome
from iris.features.definition import FeatureDefinition
from iris.features.proactive_talk.goals import GoalProposer, action_plan_from_goal
from iris.features.proactive_talk.policy import (
    policy_summary,
    proactive_action_preferences,
    proactive_policy_constraints,
)
from iris.features.proactive_talk.prompts import build_proactive_talk_prompt
from iris.features.proactive_talk.scoring import SalienceScorer

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame
    from iris.features.proactive_talk.generation import ProactiveTextGenerator
    from iris.features.proactive_talk.models import ProactiveGoal, ProactiveSalience


class ProactivePolicyStep(PipelineStep[PolicyResult]):
    """プロアクティブ発話固有の制約でポリシーを拡張するパイプラインステップ。"""

    name = "proactive_policy"

    @override
    async def run(self, frame: WorkspaceFrame) -> PolicyResult:
        """フレームに対してプロアクティブポリシー制約とプリファレンスを評価する。

        Args:
            frame: Typed workspace frame for the current cognitive cycle.

        Returns:
            PolicyResult: 評価された制約とアクション優先度を含む結果。
        """
        constraints = proactive_policy_constraints(frame)
        preferences = proactive_action_preferences(constraints)
        all_constraints = frame.constraints + constraints
        return PolicyResult(
            step_name=self.name,
            status=StepStatus.OK,
            constraints=all_constraints,
            action_preferences=frame.action_preferences + preferences,
            response_allowed=not any(constraint.blocks_response for constraint in all_constraints),
            policy_summary=policy_summary(all_constraints),
        )


class ProactiveActionSelectionStep(PipelineStep[ActionSelectionResult]):
    """顕著性スコアに基づいてプロアクティブ発話アクションを選択するパイプラインステップ。"""

    name = "proactive_action_selection"

    def __init__(
        self,
        scorer: SalienceScorer | None = None,
        proposer: GoalProposer | None = None,
        generator: ProactiveTextGenerator | None = None,
    ) -> None:
        """オプションのスコアラとゴール提案器で初期化する。

        Args:
            scorer: Salience scorer instance. Defaults to SalienceScorer().
            proposer: Goal proposer instance. Defaults to GoalProposer().
            generator: Optional bounded text generator.
        """
        self._scorer = scorer or SalienceScorer()
        self._proposer = proposer or GoalProposer()
        self._generator = generator

    @override
    async def run(self, frame: WorkspaceFrame) -> ActionSelectionResult:
        """顕著性をスコアリングし、ゴールを提案し、アクション選択結果を返す。

        Args:
            frame: Typed workspace frame for the current cognitive cycle.

        Returns:
            ActionSelectionResult: 生成されたアクションプランを含む結果。
        """
        salience = self._scorer.score(frame)
        goal = self._proposer.propose(salience)
        generator = self._generator
        if generator is not None:
            return await self._generate_candidate(frame, goal, salience, generator)
        plan = action_plan_from_goal(goal)
        return ActionSelectionResult(
            step_name=self.name,
            status=StepStatus.OK,
            action_plans=(plan,),
        )

    async def _generate_candidate(
        self,
        frame: WorkspaceFrame,
        goal: ProactiveGoal,
        salience: ProactiveSalience,
        generator: ProactiveTextGenerator,
    ) -> ActionSelectionResult:
        if not goal.should_speak:
            _log_decision("skipped", goal.reason, salience)
            return ActionSelectionResult(
                step_name=self.name,
                status=StepStatus.SKIPPED,
                reason=goal.reason,
                action_plans=(ActionPlan.no_action(),),
            )
        prompt = build_proactive_talk_prompt(frame)
        if prompt is None:
            _log_decision("skipped", "not_idle_tick", salience)
            return ActionSelectionResult(
                step_name=self.name,
                status=StepStatus.SKIPPED,
                reason="not_idle_tick",
                action_plans=(ActionPlan.no_action(),),
            )
        result = await generator.generate(prompt)
        if result.outcome is not ProactiveGenerationOutcome.GENERATED or result.text is None:
            _log_decision(result.outcome.value, result.reason, salience)
            return ActionSelectionResult(
                step_name=self.name,
                status=StepStatus.SKIPPED,
                reason=result.reason,
                action_plans=(ActionPlan.no_action(),),
            )
        _log_decision("generated", result.reason, salience)
        return ActionSelectionResult(
            step_name=self.name,
            status=StepStatus.OK,
            reason=result.reason,
            action_plans=(
                ActionPlan(
                    turn_intent="proactive_talk",
                    candidate_text=result.text,
                    should_respond=True,
                    priority=goal.priority,
                ),
            ),
        )


def define_proactive_talk_feature(
    salience_threshold: float = 0.5,
    *,
    generator: ProactiveTextGenerator | None = None,
) -> FeatureDefinition:
    """プロアクティブ発話機能のFeatureDefinitionを作成する。

    Args:
        salience_threshold: Minimum salience score to trigger proactive talk.
        generator: Optional bounded proactive text generator.

    Returns:
        A configured FeatureDefinition with proactive talk pipeline steps.
    """
    scorer = SalienceScorer(threshold=salience_threshold)
    return FeatureDefinition(
        name="proactive_talk",
        cognitive_steps=(
            ProactivePolicyStep(),
            ProactiveActionSelectionStep(
                scorer=scorer,
                proposer=GoalProposer(),
                generator=generator,
            ),
        ),
    )


def _log_decision(outcome: str, reason: str, salience: ProactiveSalience) -> None:
    logger.info(
        "runtime.proactive.decision",
        outcome=outcome,
        reason=reason,
        salience_score=round(salience.score, 4),
        salience_threshold=round(salience.threshold, 4),
    )
