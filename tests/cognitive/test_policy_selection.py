"""ポリシー対応応答プロンプト構築のテスト。"""

from __future__ import annotations

from datetime import UTC, datetime

from iris.cognitive.action.response import build_response_prompt
from iris.cognitive.workspace.frame import InterpretedInput, WorkspaceFrame
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import ActorMessageObservation, ObservationKind
from iris.contracts.policy import PolicyConstraint
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId


def _frame(constraints: tuple[PolicyConstraint, ...] = ()) -> WorkspaceFrame:
    """オプションのポリシー制約を持つWorkspaceFrameを返す。

    Returns:
        WorkspaceFrame: 構築済みのワークスペースフレーム。
    """
    return WorkspaceFrame(
        observation=ActorMessageObservation(
            observation_id=ObservationId("obs-policy-prompt"),
            session_id=SessionId("session-policy-prompt"),
            actor=Identity(
                actor_id=ActorId("actor-policy-prompt"),
                actor_kind=ActorKind.HUMAN,
                display_name="Mina",
                provider="test",
                provider_subject=ExternalRef("mina"),
            ),
            space_id=None,
            occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
            kind=ObservationKind.ACTOR_MESSAGE,
            text="hello",
        ),
        interpreted_input=InterpretedInput(text="hello", language=None),
        constraints=constraints,
    )


def test_policy_prompt_context_appears_only_when_present() -> None:
    """ポリシープロンプト命令が制約が存在する場合のみ含まれることを確認する。"""
    prompt_without_policy = build_response_prompt(_frame())
    prompt_with_policy = build_response_prompt(
        _frame(
            (
                PolicyConstraint(
                    name="calm_response",
                    reason="high arousal",
                    prompt_instruction="keep tone calm",
                ),
            )
        )
    )

    assert prompt_without_policy is not None
    assert prompt_without_policy.constraints == ()
    assert prompt_with_policy is not None
    assert prompt_with_policy.constraints == ("keep tone calm",)
