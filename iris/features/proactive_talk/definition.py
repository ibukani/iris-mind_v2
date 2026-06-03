"""プロアクティブ発話機能のパイプラインステップとファクトリ。"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast, override

from iris.cognitive.cycle.models import ActionSelectionResult, PolicyResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.features.definition import FeatureDefinition
from iris.features.proactive_talk.goals import GoalProposer, action_plan_from_goal
from iris.features.proactive_talk.policy import (
    policy_summary,
    proactive_action_preferences,
    proactive_policy_constraints,
)
from iris.features.proactive_talk.scoring import SalienceScorer

if TYPE_CHECKING:
    from iris.features.proactive_talk.models import ProactiveFrameContext


class ProactivePolicyStep(PipelineStep[PolicyResult]):
    """プロアクティブ発話固有の制約でポリシーを拡張するパイプラインステップ。"""

    name = "proactive_policy"

    @override
    async def run(self, frame: object) -> PolicyResult:
        """フレームに対してプロアクティブポリシー制約とプリファレンスを評価する。

        Returns:
            PolicyResult: 評価された制約とアクション優先度を含む結果。
        """
        proactive_frame = cast("ProactiveFrameContext", frame)
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
    """顕著性スコアに基づいてプロアクティブ発話アクションを選択するパイプラインステップ。"""

    name = "proactive_action_selection"

    def __init__(
        self,
        scorer: SalienceScorer | None = None,
        proposer: GoalProposer | None = None,
    ) -> None:
        """オプションのスコアラとゴール提案器で初期化する。

        Args:
            scorer: Salience scorer instance. Defaults to SalienceScorer().
            proposer: Goal proposer instance. Defaults to GoalProposer().
        """
        self._scorer = scorer or SalienceScorer()
        self._proposer = proposer or GoalProposer()

    @override
    async def run(self, frame: object) -> ActionSelectionResult:
        """顕著性をスコアリングし、ゴールを提案し、アクション選択結果を返す。

        Returns:
            ActionSelectionResult: 生成されたアクションプランを含む結果。
        """
        proactive_frame = cast("ProactiveFrameContext", frame)
        salience = self._scorer.score(proactive_frame)
        goal = self._proposer.propose(salience)
        plan = action_plan_from_goal(goal)
        return ActionSelectionResult(
            step_name=self.name,
            status=StepStatus.OK,
            action_plans=(plan,),
        )


def define_proactive_talk_feature(salience_threshold: float = 0.5) -> FeatureDefinition:
    """プロアクティブ発話機能のFeatureDefinitionを作成する。

    Args:
        salience_threshold: Minimum salience score to trigger proactive talk.

    Returns:
        A configured FeatureDefinition with proactive talk pipeline steps.
    """
    scorer = SalienceScorer(threshold=salience_threshold)
    return FeatureDefinition(
        name="proactive_talk",
        pipeline_steps=(
            ProactivePolicyStep(),
            ProactiveActionSelectionStep(scorer=scorer, proposer=GoalProposer()),
        ),
    )
