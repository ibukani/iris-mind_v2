"""RelationshipStep の永続化動作テスト。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.adapters.relationship.sqlite import SQLiteRelationshipStore
from iris.cognitive.affect.relationship import RelationshipStep
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import AppraisalResult, StepStatus
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId

if TYPE_CHECKING:
    from pathlib import Path

    from iris.cognitive.workspace.frame import WorkspaceFrame


def _actor() -> Identity:
    return Identity(
        actor_id=ActorId("actor-persistent-relationship"),
        actor_kind=ActorKind.HUMAN,
        display_name="Mina",
        provider="test",
        provider_subject=ExternalRef("mina"),
    )


def _message(observation_id: str) -> ActorMessageObservation:
    return ActorMessageObservation(
        observation_id=ObservationId(observation_id),
        session_id=SessionId("session-persistent-relationship"),
        context=ObservationContext(actor=_actor()),
        occurred_at=datetime(2026, 6, 24, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="thanks, that helped",
    )


def _frame(observation_id: str, *, valence: float = 0.7) -> WorkspaceFrame:
    builder = FrameBuilder()
    frame = builder.build_initial(_message(observation_id))
    return builder.apply(
        frame,
        AppraisalResult(
            step_name="appraisal",
            status=StepStatus.OK,
            mood_label="positive",
            valence=valence,
            arousal=0.2,
            dominance=0.1,
            affect_summary="positive affect",
        ),
    )


@pytest.mark.anyio
async def test_positive_affect_increases_affinity_and_trust(tmp_path: Path) -> None:
    """Positive affect は affinity/trust を上げる。"""
    db_path = tmp_path / "positive.db"
    store = SQLiteRelationshipStore(db_path)

    result = await RelationshipStep(store).run(_frame("obs-positive"))

    assert result.status == StepStatus.OK
    assert result.affinity > 0.0
    assert result.trust > 0.5


@pytest.mark.anyio
async def test_repeated_turns_increase_familiarity(tmp_path: Path) -> None:
    """同じ actor の turn が重なると familiarity が増える。"""
    db_path = tmp_path / "repeat.db"
    store = SQLiteRelationshipStore(db_path)

    first = await RelationshipStep(store).run(_frame("obs-repeat-1"))
    second = await RelationshipStep(store).run(_frame("obs-repeat-2"))

    assert first.status == StepStatus.OK
    assert second.status == StepStatus.OK
    assert second.familiarity > first.familiarity


@pytest.mark.anyio
async def test_relationship_survives_sqlite_store_reload(tmp_path: Path) -> None:
    """Relationship state は同じ SQLite DB path の store 再生成後も残る。"""
    db_path = tmp_path / "state.db"
    actor = _actor()

    await RelationshipStep(SQLiteRelationshipStore(db_path)).run(_frame("obs-reload"))

    reloaded = SQLiteRelationshipStore(db_path).get(actor.actor_id)
    assert reloaded is not None
    assert reloaded.actor_id == actor.actor_id
    assert reloaded.source_observation_id == ObservationId("obs-reload")
    assert reloaded.familiarity > 0.0
