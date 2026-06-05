"""関係性追跡パイプラインステップのテスト。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.cognitive.affect.relationship import InMemoryRelationshipState, RelationshipStep
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import AppraisalResult, StepStatus
from iris.cognitive.workspace.frame import RelationshipSnapshot
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import AccountId, ActorId, ExternalRef, ObservationId, SessionId
from tests.helpers.approx import approx


def actor_message(actor: Identity | None = None) -> ActorMessageObservation:
    """オプションのアクターIDを持つActorMessageObservationを返す。

    Returns:
        ActorMessageObservation: 構築済みの観測。
    """
    return ActorMessageObservation(
        observation_id=ObservationId("obs-relationship"),
        session_id=SessionId("session-relationship"),
        context=ObservationContext(actor=actor),
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="thanks",
    )


@pytest.mark.anyio
async def test_relationship_step_updates_per_user_state() -> None:
    """RelationshipStepがユーザーごとの親密度、信頼度、熟知度を更新することを確認する。"""
    actor = Identity(
        actor_id=ActorId("actor-relationship"),
        actor_kind=ActorKind.HUMAN,
        display_name="Mina",
        provider="test",
        provider_subject=ExternalRef("mina"),
    )
    state = InMemoryRelationshipState()
    builder = FrameBuilder()
    frame = FrameBuilder().build_initial(actor_message(actor))
    frame = builder.apply(
        frame,
        AppraisalResult(step_name="appraisal", status=StepStatus.OK, valence=0.5),
    )

    result = await RelationshipStep(state).run(frame)
    enriched = builder.apply(frame, result)

    assert result.status == StepStatus.OK
    assert enriched.relationship.actor_label == "Mina"
    assert enriched.relationship.affinity == approx(0.02)
    assert enriched.relationship.trust == approx(0.515)
    assert enriched.relationship.familiarity == approx(0.02)
    assert enriched.relationship.relationship_summary is not None


@pytest.mark.anyio
async def test_relationship_step_skips_without_actor_identity() -> None:
    """観測にアクターIDがない場合にRelationshipStepがスキップすることを確認する。"""
    result = await RelationshipStep().run(
        FrameBuilder().build_initial(actor_message()),
    )

    assert result.status == StepStatus.SKIPPED
    assert result.reason == "no actor identity"


@pytest.mark.anyio
async def test_relationship_step_uses_actor_id_not_account_id_as_state_key() -> None:
    """RelationshipStepがAccountIdではなくActorIdで関係状態を読むことを確認する。"""
    actor = Identity(
        actor_id=ActorId("actor-key"),
        actor_kind=ActorKind.HUMAN,
        display_name="Mina",
        provider="test",
        provider_subject=ExternalRef("mina"),
        account_id=AccountId("account-one"),
    )
    state = InMemoryRelationshipState()
    state.set(
        ActorId("actor-key"),
        RelationshipSnapshot(
            actor_label="Mina",
            affinity=0.8,
            trust=0.8,
            familiarity=0.8,
            relationship_summary="seeded by actor",
        ),
    )
    frame = FrameBuilder().build_initial(actor_message(actor))
    frame = FrameBuilder().apply(
        frame,
        AppraisalResult(step_name="appraisal", status=StepStatus.OK, valence=0.0),
    )

    result = await RelationshipStep(state).run(frame)

    assert result.status == StepStatus.OK
    assert result.actor_label == "Mina"
    assert result.affinity > 0.7
