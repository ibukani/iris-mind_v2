"""AffectPersistenceStep のテスト。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.cognitive.affect.appraisal import classify_appraisal
from iris.cognitive.affect.persistence import AffectBaselineLoadStep, AffectPersistenceStep
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import AppraisalResult, PerceptionResult, StepStatus
from iris.contracts.affect import AffectBaselineRecord, AffectScope
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId
from iris.runtime.state.ephemeral.affect import InMemoryAffectStore
from tests.helpers.approx import approx

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame


def _message(observation_id: str = "obs-affect") -> ActorMessageObservation:
    actor = Identity(
        actor_id=ActorId("actor-affect"),
        actor_kind=ActorKind.HUMAN,
        display_name="Mina",
        provider="test",
        provider_subject=ExternalRef("mina"),
    )
    return ActorMessageObservation(
        observation_id=ObservationId(observation_id),
        session_id=SessionId("session-affect"),
        context=ObservationContext(actor=actor),
        occurred_at=datetime(2026, 6, 24, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="thanks",
    )


def _frame(
    *,
    observation_id: str = "obs-affect",
    mood_label: str | None = "positive",
    valence: float = 0.6,
    arousal: float = 0.2,
    dominance: float = 0.1,
    affect_summary: str | None = None,
) -> WorkspaceFrame:
    builder = FrameBuilder()
    frame = builder.build_initial(_message(observation_id))
    summary = affect_summary
    if summary is None and mood_label != "neutral":
        summary = mood_label
    frame = builder.apply(
        frame,
        PerceptionResult(
            step_name="perception",
            status=StepStatus.OK,
            text="thanks",
        ),
    )
    return builder.apply(
        frame,
        AppraisalResult(
            step_name="appraisal",
            status=StepStatus.OK,
            mood_label=mood_label,
            valence=valence,
            arousal=arousal,
            dominance=dominance,
            affect_summary=summary,
        ),
    )


@pytest.mark.anyio
async def test_affect_baseline_load_skips_when_store_empty() -> None:
    """保存済み baseline がない場合は frame を変更しない。"""
    store = InMemoryAffectStore()
    frame = _frame()

    result = await AffectBaselineLoadStep(store).run(frame)
    updated = FrameBuilder.apply(frame, result)

    assert result.status == StepStatus.SKIPPED
    assert result.reason == "missing_affect_baseline"
    assert updated == frame


@pytest.mark.anyio
async def test_affect_baseline_load_populates_frame_affect() -> None:
    """保存済み global baseline を frame.affect に反映する。"""
    store = InMemoryAffectStore()
    await store.upsert_global(
        AffectBaselineRecord(
            scope=AffectScope.GLOBAL,
            mood_label="positive",
            valence=0.5,
            arousal=0.2,
            dominance=0.1,
            affect_summary="positive VAD(0.50, 0.20, 0.10)",
        ),
    )
    frame = FrameBuilder().build_initial(_message("obs-affect-load"))

    result = await AffectBaselineLoadStep(store).run(frame)
    updated = FrameBuilder.apply(frame, result)

    assert result.status == StepStatus.OK
    assert updated.affect.mood_label == "positive"
    assert updated.affect.valence == approx(0.5)
    assert updated.affect.arousal == approx(0.2)
    assert updated.affect.dominance == approx(0.1)
    assert updated.affect.affect_summary == "positive VAD(0.50, 0.20, 0.10)"


@pytest.mark.anyio
async def test_appraisal_affect_is_persisted_to_global_baseline() -> None:
    """Appraisal の affect を global baseline として保存する。"""
    store = InMemoryAffectStore()

    result = await AffectPersistenceStep(store).run(
        _frame(observation_id="obs-affect-persist"),
    )

    stored = await store.get_global()
    assert result.status == StepStatus.OK
    assert result.persisted
    assert stored is not None
    assert stored.scope == AffectScope.GLOBAL
    assert stored.actor_id is None
    assert stored.valence == approx(0.6)
    assert stored.source_observation_id == ObservationId("obs-affect-persist")


@pytest.mark.anyio
async def test_affect_baseline_uses_conservative_smoothing() -> None:
    """既存 baseline がある場合は 0.9/0.1 で保守的に更新する。"""
    store = InMemoryAffectStore()
    step = AffectPersistenceStep(store)

    await step.run(_frame(observation_id="obs-affect-1", valence=0.6))
    result = await step.run(
        _frame(
            observation_id="obs-affect-2",
            mood_label="negative",
            valence=-0.4,
        ),
    )

    stored = await store.get_global()
    assert result.status == StepStatus.OK
    assert stored is not None
    assert stored.valence == approx(0.5)
    assert stored.source_observation_id == ObservationId("obs-affect-2")


@pytest.mark.anyio
async def test_missing_interpreted_input_skips_affect_persistence() -> None:
    """Interpreted input がない場合は affect persistence を skip する。"""
    store = InMemoryAffectStore()
    builder = FrameBuilder()
    frame = builder.apply(
        builder.build_initial(_message("obs-affect-missing-input")),
        AppraisalResult(
            step_name="appraisal",
            status=StepStatus.OK,
            mood_label="positive",
            valence=0.6,
        ),
    )

    result = await AffectPersistenceStep(store).run(frame)

    assert result.status == StepStatus.SKIPPED
    assert result.reason == "missing_interpreted_input"
    loaded = await store.get_global()
    assert loaded is None


@pytest.mark.anyio
async def test_no_affect_skips_affect_persistence() -> None:
    """有意な affect がない場合は baseline を更新しない。"""
    store = InMemoryAffectStore()

    result = await AffectPersistenceStep(store).run(
        _frame(mood_label=None, valence=0.0, arousal=0.0, dominance=0.0),
    )

    assert result.status == StepStatus.SKIPPED
    assert result.reason == "no_meaningful_affect"
    loaded = await store.get_global()
    assert loaded is None


@pytest.mark.anyio
async def test_neutral_appraisal_summary_does_not_persist_affect() -> None:
    """Neutral VAD summary だけでは affect baseline を更新しない。"""
    store = InMemoryAffectStore()
    affect = classify_appraisal("what tea do I like?")

    assert affect.mood_label is None
    assert affect.valence == approx(0.0)
    assert affect.arousal == approx(0.0)
    assert affect.dominance == approx(0.0)
    assert affect.affect_summary is not None

    result = await AffectPersistenceStep(store).run(
        _frame(
            mood_label=affect.mood_label,
            valence=affect.valence,
            arousal=affect.arousal,
            dominance=affect.dominance,
            affect_summary=affect.affect_summary,
        ),
    )

    assert result.status == StepStatus.SKIPPED
    assert result.reason == "no_meaningful_affect"
    loaded = await store.get_global()
    assert loaded is None
