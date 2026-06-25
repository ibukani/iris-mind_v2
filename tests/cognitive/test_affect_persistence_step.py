"""AffectPersistenceStep のテスト。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.adapters.affect.memory import InMemoryAffectStore
from iris.cognitive.affect.persistence import AffectPersistenceStep
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import AppraisalResult, PerceptionResult, StepStatus
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId
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
) -> WorkspaceFrame:
    builder = FrameBuilder()
    frame = builder.build_initial(_message(observation_id))
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
            affect_summary=None if mood_label == "neutral" else mood_label,
        ),
    )


@pytest.mark.anyio
async def test_appraisal_affect_is_persisted_to_global_baseline() -> None:
    """Appraisal の affect を global baseline として保存する。"""
    store = InMemoryAffectStore()

    result = await AffectPersistenceStep(store).run(
        _frame(observation_id="obs-affect-persist"),
    )

    stored = store.get_global()
    assert result.status == StepStatus.OK
    assert result.persisted
    assert stored is not None
    assert stored.scope == "global"
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

    stored = store.get_global()
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
    assert store.get_global() is None


@pytest.mark.anyio
async def test_no_affect_skips_affect_persistence() -> None:
    """有意な affect がない場合は baseline を更新しない。"""
    store = InMemoryAffectStore()

    result = await AffectPersistenceStep(store).run(
        _frame(mood_label="neutral", valence=0.0, arousal=0.0, dominance=0.0),
    )

    assert result.status == StepStatus.SKIPPED
    assert result.reason == "no_meaningful_affect"
    assert store.get_global() is None
