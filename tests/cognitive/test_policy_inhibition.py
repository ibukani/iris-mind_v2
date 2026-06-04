"""ポリシー抑制パイプラインステップと制約生成のテスト。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import PolicyResult, StepStatus
from iris.cognitive.perception.basic import SimplePerceptionStep
from iris.cognitive.policy.inhibition import PolicyInhibitionStep
from iris.cognitive.workspace.frame import AffectSnapshot, RelationshipSnapshot, WorkspaceFrame
from iris.contracts.actions import ActionPlan
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import ObservationKind, UserMessageObservation
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId


def _observation(text: str = "hello") -> UserMessageObservation:
    """指定されたテキストとテスト用IDを持つUserMessageObservationを返す。

    Returns:
        UserMessageObservation: 構築済みの観測。
    """
    return UserMessageObservation(
        observation_id=ObservationId("obs-policy"),
        session_id=SessionId("session-policy"),
        actor=Identity(
            actor_id=ActorId("actor-policy"),
            actor_kind=ActorKind.HUMAN,
            display_name="Mina",
            provider="test",
            provider_subject=ExternalRef("mina"),
        ),
        space_id=None,
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.USER_MESSAGE,
        text=text,
    )


@pytest.mark.anyio
async def test_policy_step_returns_typed_result_without_mutating_frame() -> None:
    """PolicyInhibitionStepが元のフレームを変更せずに型付き制約を返すことを確認する。"""
    frame = WorkspaceFrame(observation=_observation("I feel unsafe"))
    builder = FrameBuilder()
    frame = builder.apply(frame, await SimplePerceptionStep().run(frame))
    enriched = replace(
        frame,
        affect=AffectSnapshot(mood_label="negative", arousal=0.9, valence=-0.8),
        relationship=RelationshipSnapshot(user_label="Mina", familiarity=0.0),
    )

    result = await PolicyInhibitionStep().run(enriched)

    assert isinstance(result, PolicyResult)
    assert result.status == StepStatus.OK
    assert [item.name for item in result.constraints] == ["calm_response", "low_familiarity"]
    assert [item.name for item in result.action_preferences] == ["prefer_calm_response"]
    assert enriched.constraints == ()


def test_frame_builder_enriches_frame_from_policy_result() -> None:
    """FrameBuilder.applyがポリシー結果データでフレームをエンリッチすることを確認する。"""
    frame = WorkspaceFrame(observation=_observation())
    result = PolicyResult(
        step_name="policy_inhibition",
        status=StepStatus.OK,
        constraints=(),
        policy_summary="policy-ready",
    )

    next_frame = FrameBuilder().apply(frame, result)

    assert frame.policy_summary is None
    assert next_frame.policy_summary == "policy-ready"


@pytest.mark.anyio
async def test_empty_response_candidate_is_marked_by_policy() -> None:
    """PolicyInhibitionStepが空の応答候補をブロックすることを確認する。"""
    frame = WorkspaceFrame(
        observation=_observation(),
        candidate_action_plans=(
            ActionPlan(
                turn_intent="respond",
                candidate_text="",
                should_respond=True,
                priority=1,
            ),
        ),
    )

    result = await PolicyInhibitionStep().run(frame)

    assert result.response_allowed is False
    assert result.constraints[0].name == "empty_response_candidate"
    assert result.constraints[0].blocks_response is True
