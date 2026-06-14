"""ポリシー契約の不変性と型階層のテスト。"""

from __future__ import annotations

from iris.cognitive.cycle.models import PipelineStepResult, PolicyResult, StepStatus
from iris.contracts.policy import ActionPreference, PolicyConstraint
from tests.helpers.immutability import assert_frozen_field


def test_policy_contracts_are_immutable_and_typed() -> None:
    """ポリシー契約がfrozenでありPipelineStepResultを継承していることを確認する。"""
    constraint = PolicyConstraint(
        name="calm_response",
        reason="high arousal with negative valence",
        prompt_instruction="keep tone calm",
    )
    preference = ActionPreference(
        name="prefer_calm_response",
        reason="policy constraint",
        priority_delta=1,
    )
    result = PolicyResult(
        step_name="policy_inhibition",
        status=StepStatus.OK,
        constraints=(constraint,),
        action_preferences=(preference,),
        policy_summary="calm_response",
    )

    assert isinstance(result, PipelineStepResult)
    assert result.constraints == (constraint,)
    assert result.action_preferences == (preference,)

    assert_frozen_field(constraint, "name", "other")
    assert_frozen_field(result, "response_allowed", value=False)
