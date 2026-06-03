from __future__ import annotations

from iris.contracts.observations import IdleTickObservation
from iris.contracts.policy import ActionPreference, PolicyConstraint
from iris.features.proactive_talk.models import ProactiveFrameContext


def proactive_policy_constraints(frame: ProactiveFrameContext) -> tuple[PolicyConstraint, ...]:
    if not isinstance(frame.observation, IdleTickObservation):
        return ()

    constraints: list[PolicyConstraint] = []
    if any(constraint.blocks_response for constraint in frame.constraints):
        constraints.append(
            PolicyConstraint(
                name="proactive_no_action",
                reason="existing policy constraint blocks response",
                prompt_instruction="do not initiate proactive talk",
                blocks_response=True,
            )
        )

    if frame.relationship.user_label is not None and frame.relationship.familiarity < 0.2:
        constraints.append(
            PolicyConstraint(
                name="proactive_low_familiarity",
                reason="relationship familiarity is low",
                prompt_instruction="avoid over-familiarity",
            )
        )

    if frame.affect.arousal > 0.75 and frame.affect.valence < -0.55:
        constraints.append(
            PolicyConstraint(
                name="proactive_calm_response",
                reason="high arousal with negative valence",
                prompt_instruction="keep tone calm",
            )
        )

    return tuple(constraints)


def proactive_action_preferences(
    constraints: tuple[PolicyConstraint, ...],
) -> tuple[ActionPreference, ...]:
    if any(constraint.name == "proactive_calm_response" for constraint in constraints):
        return (
            ActionPreference(
                name="prefer_calm_proactive_talk",
                reason="proactive policy calm-response constraint",
                priority_delta=1,
            ),
        )
    return ()


def policy_summary(constraints: tuple[PolicyConstraint, ...]) -> str | None:
    if not constraints:
        return None
    return "; ".join(constraint.name for constraint in constraints)
