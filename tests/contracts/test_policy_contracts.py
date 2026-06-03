from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from iris.cognitive.cycle.models import PipelineStepResult, PolicyResult, StepStatus
from iris.cognitive.workspace.frame import ActionPreference, PolicyConstraint


def test_policy_contracts_are_immutable_and_typed() -> None:
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

    with pytest.raises(FrozenInstanceError):
        constraint.name = "other"

    with pytest.raises(FrozenInstanceError):
        result.response_allowed = False
