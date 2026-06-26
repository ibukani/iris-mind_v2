"""関係性追跡パイプラインステップのテスト。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.adapters.relationship.memory import InMemoryRelationshipStore
from iris.cognitive.affect.relationship import RelationshipStep
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import AppraisalResult, PerceptionResult, StepStatus
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.contracts.relationship import RelationshipSnapshotRecord
from iris.core.ids import AccountId, ActorId, ExternalRef, ObservationId, SessionId

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame


def _actor() -> Identity:
    return Identity(
        actor_id=ActorId("actor-relationship"),
        actor_kind=ActorKind.HUMAN,
        display_name="Mina",
        provider="test",
        provider_subject=ExternalRef("mina"),
    )


def _actor_message(
    actor: Identity | None = None,
    *,
    observation_id: ObservationId | None = None,
    account_id: AccountId | None = None,
) -> ActorMessageObservation:
    actual_observation_id = observation_id or ObservationId("obs-relationship")
    return ActorMessageObservation(
        observation_id=actual_observation_id,
        session_id=SessionId("session-relationship"),
        context=ObservationContext(actor=actor, account_id=account_id),
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="thanks",
    )


def _positive_frame(actor: Identity) -> WorkspaceFrame:
    builder = FrameBuilder()
    frame = builder.build_initial(_actor_message(actor))
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
            mood_label="positive",
            valence=0.8,
            arousal=0.2,
            dominance=0.1,
            affect_summary="positive",
        ),
    )


@pytest.mark.anyio
async def test_relationship_step_updates_actor_scoped_store() -> None:
    """RelationshipStep は ActorId ごとの関係性 state を更新する。"""
    actor = _actor()
    store = InMemoryRelationshipStore()

    result = await RelationshipStep(store).run(_positive_frame(actor))

    stored = store.get(actor.actor_id)
    assert result.status == StepStatus.OK
    assert result.actor_label == "Mina"
    assert result.affinity > 0.0
    assert result.trust > 0.5
    assert result.familiarity > 0.0
    assert stored is not None
    assert stored.actor_id == actor.actor_id
    assert stored.source_observation_id == ObservationId("obs-relationship")


@pytest.mark.anyio
async def test_relationship_step_skips_without_actor_identity() -> None:
    """観測に actor がない場合は関係性 state を更新しない。"""
    store = InMemoryRelationshipStore()
    result = await RelationshipStep(store).run(
        FrameBuilder().build_initial(_actor_message()),
    )

    assert result.status == StepStatus.SKIPPED
    assert result.reason == "missing_actor"


@pytest.mark.anyio
async def test_relationship_step_uses_actor_id_not_account_id_as_state_key() -> None:
    """RelationshipStep は AccountId ではなく ActorId で既存 state を読む。"""
    actor = _actor()
    store = InMemoryRelationshipStore()
    store.upsert(
        RelationshipSnapshotRecord(
            actor_id=actor.actor_id,
            actor_label="Existing Mina",
            affinity=0.4,
            trust=0.7,
            familiarity=0.3,
        ),
    )
    builder = FrameBuilder()
    frame = builder.build_initial(
        _actor_message(actor, account_id=AccountId("account-different")),
    )
    frame = builder.apply(
        frame,
        PerceptionResult(
            step_name="perception",
            status=StepStatus.OK,
            text="thanks",
        ),
    )
    frame = builder.apply(
        frame,
        AppraisalResult(
            step_name="appraisal",
            status=StepStatus.OK,
            mood_label="positive",
            valence=0.5,
            arousal=0.0,
            dominance=0.0,
        ),
    )

    result = await RelationshipStep(store).run(frame)

    assert result.status == StepStatus.OK
    assert result.actor_label == "Existing Mina"
    assert result.familiarity > 0.3
