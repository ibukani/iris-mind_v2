"""アフェクトアプレイザルパイプラインステップとキーワード分類のテスト。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.cognitive.affect.appraisal import AppraisalStep, classify_appraisal
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import StepStatus
from iris.cognitive.perception.basic import SimplePerceptionStep
from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import ObservationId, SessionId
from tests.helpers.approx import approx


def actor_message(text: str) -> ActorMessageObservation:
    """指定されたテキストを持つActorMessageObservationを返す。

    Returns:
        ActorMessageObservation: 構築済みの観測。
    """
    return ActorMessageObservation(
        observation_id=ObservationId("obs-affect"),
        session_id=SessionId("session-affect"),
        context=ObservationContext(),
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )


def test_keyword_appraisal_is_deterministic() -> None:
    """キーワードベースのアフェクト分類が決定論的なVAD値を生成することを確認する。"""
    affect = classify_appraisal("ありがとう、助かった。急ぎで不安だった")

    assert affect.mood_label == "positive"
    assert affect.valence == approx(0.25)
    assert affect.arousal == approx(0.30000000000000004)
    assert affect.dominance == approx(0.0)
    assert affect.affect_summary == "positive VAD(v=0.25, a=0.30, d=0.00)"


@pytest.mark.anyio
async def test_appraisal_step_enriches_frame_through_frame_builder() -> None:
    """AppraisalStepがFrameBuilder.apply()を通じてエンリッチメントを生成することを確認する。"""
    builder = FrameBuilder()
    frame = WorkspaceFrame(observation=actor_message("I am confused and need help urgent"))
    frame = builder.apply(frame, await SimplePerceptionStep().run(frame))

    result = await AppraisalStep().run(frame)
    enriched = builder.apply(frame, result)

    assert result.status == StepStatus.OK
    assert enriched.affect.mood_label == "uncertain"
    assert enriched.affect.dominance < 0.0
    assert enriched.affect.affect_summary is not None
