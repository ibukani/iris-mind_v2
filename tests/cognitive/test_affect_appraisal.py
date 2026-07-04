"""アフェクトアプレイザルパイプラインステップとキーワード分類のテスト。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.cognitive.affect.appraisal import (
    AppraisalStep,
    classify_appraisal,
    classify_appraisal_signals,
)
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import StepStatus
from iris.cognitive.perception.basic import SimplePerceptionStep
from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.appraisal import AppraisalSafetyHintKind, AppraisalSignalKind
from iris.contracts.companion_affect import CompanionAffectStateKind
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

    result = await AppraisalStep(appraisal_signals_enabled=True).run(frame)
    enriched = builder.apply(frame, result)

    assert result.status == StepStatus.OK
    assert enriched.affect.mood_label == "uncertain"
    assert enriched.affect.dominance < 0.0
    assert enriched.affect.affect_summary is not None
    assert enriched.appraisal.signals
    assert enriched.appraisal.summary is not None


def test_appraisal_signals_separate_user_emotion_from_relationship_attitude() -> None:
    """「今日は悲しい」は user emotion であり relationship attitude ではない。"""
    signals = classify_appraisal_signals("今日は悲しい")

    assert tuple(signal.kind for signal in signals) == (AppraisalSignalKind.USER_EMOTION,)
    assert signals[0].state_boundary is CompanionAffectStateKind.ACTOR_AFFECT_TRACE
    assert signals[0].source_span.text == "悲しい"


def test_appraisal_signals_separate_iris_attitude() -> None:
    """Iris への好意 / 不満は attitude_toward_iris として分離する。"""
    positive = classify_appraisal_signals("Irisが好き、ありがとう")
    negative = classify_appraisal_signals("Irisは役に立たない")

    assert tuple(signal.kind for signal in positive) == (AppraisalSignalKind.ATTITUDE_TOWARD_IRIS,)
    assert positive[0].polarity > 0.0
    assert positive[0].state_boundary is CompanionAffectStateKind.ACTOR_RELATIONSHIP
    assert tuple(signal.kind for signal in negative) == (AppraisalSignalKind.ATTITUDE_TOWARD_IRIS,)
    assert negative[0].polarity < 0.0


def test_appraisal_signals_separate_topic_sentiment_from_relationship() -> None:
    """Topic sentiment は relationship update source と混ざらない。"""
    signals = classify_appraisal_signals("この映画は最悪")

    assert tuple(signal.kind for signal in signals) == (AppraisalSignalKind.TOPIC_SENTIMENT,)
    assert signals[0].state_boundary is CompanionAffectStateKind.RECENT_INTERACTION_TONE


def test_appraisal_signals_separate_care_intent() -> None:
    """Care intent は relationship / dependency-risk と別 signal になる。"""
    signals = classify_appraisal_signals("大丈夫?無理しないで")

    assert tuple(signal.kind for signal in signals) == (AppraisalSignalKind.CARE_INTENT,)
    assert signals[0].label == "care_intent"
    assert signals[0].state_boundary is CompanionAffectStateKind.RECENT_INTERACTION_TONE


def test_appraisal_signals_can_emit_dependency_risk_safety_hint() -> None:
    """dependency-risk hint は #82 側に渡せる safety hint を持つ。"""
    signals = classify_appraisal_signals("君がいないと生きていけない")

    assert tuple(signal.kind for signal in signals) == (AppraisalSignalKind.DEPENDENCY_RISK_HINT,)
    assert signals[0].safety_hint is AppraisalSafetyHintKind.DEPENDENCY_RISK
    assert signals[0].state_boundary is None


def test_appraisal_step_can_disable_typed_signals_by_config_gate() -> None:
    """Classifier helper は deterministic だが step の初期有効化は config-gated。"""
    result = classify_appraisal("Irisが好き")

    assert result.valence > 0.0
    assert classify_appraisal_signals("Irisが好き")


@pytest.mark.anyio
async def test_appraisal_step_default_omits_typed_signals_until_config_enabled() -> None:
    """AppraisalStep 単体の既定値も config-gated として typed signal を出さない。"""
    builder = FrameBuilder()
    frame = WorkspaceFrame(observation=actor_message("Irisが好き"))
    frame = builder.apply(frame, await SimplePerceptionStep().run(frame))

    result = await AppraisalStep().run(frame)

    assert result.status == StepStatus.OK
    assert result.valence > 0.0
    assert result.appraisal_signals == ()
    assert result.appraisal_summary is None


@pytest.mark.anyio
async def test_appraisal_step_runtime_gate_omits_signals() -> None:
    """AppraisalStep の runtime gate が typed signal 生成だけを止める。"""
    builder = FrameBuilder()
    frame = WorkspaceFrame(observation=actor_message("Irisが好き"))
    frame = builder.apply(frame, await SimplePerceptionStep().run(frame))

    result = await AppraisalStep(appraisal_signals_enabled=False).run(frame)
    enriched = builder.apply(frame, result)

    assert result.status == StepStatus.OK
    assert result.valence > 0.0
    assert result.appraisal_signals == ()
    assert enriched.appraisal.signals == ()
