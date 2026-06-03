"""プロアクティブ発話のポリシー制約・プリファレンスロジック。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.contracts.observations import IdleTickObservation
from iris.contracts.policy import ActionPreference, PolicyConstraint

_LOW_FAMILIARITY_THRESHOLD = 0.2
_HIGH_AROUSAL_THRESHOLD = 0.75
_NEGATIVE_VALENCE_THRESHOLD = -0.55

if TYPE_CHECKING:
    from iris.features.proactive_talk.models import ProactiveFrameContext


def proactive_policy_constraints(frame: ProactiveFrameContext) -> tuple[PolicyConstraint, ...]:
    """フレームからプロアクティブ発話固有のポリシー制約を生成する。

    Returns:
        tuple[PolicyConstraint, ...]: 生成されたポリシー制約のタプル。
    """
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

    if (
        frame.relationship.user_label is not None
        and frame.relationship.familiarity < _LOW_FAMILIARITY_THRESHOLD
    ):
        constraints.append(
            PolicyConstraint(
                name="proactive_low_familiarity",
                reason="relationship familiarity is low",
                prompt_instruction="avoid over-familiarity",
            )
        )

    if (
        frame.affect.arousal > _HIGH_AROUSAL_THRESHOLD
        and frame.affect.valence < _NEGATIVE_VALENCE_THRESHOLD
    ):
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
    """プロアクティブポリシー制約に基づいてアクション優先度を生成する。

    Returns:
        tuple[ActionPreference, ...]: 生成されたアクション優先度のタプル。
    """
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
    """アクティブなポリシー制約を文字列に要約する。空の場合はNone。

    Returns:
        str | None: 制約のサマリー文字列。空の場合は None。
    """
    if not constraints:
        return None
    return "; ".join(constraint.name for constraint in constraints)
