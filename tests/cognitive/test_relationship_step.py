"""関係性追跡パイプラインステップのテスト。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.cognitive.affect.appraisal import classify_appraisal_signals
from iris.cognitive.affect.relationship import RelationshipStep
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import AppraisalResult, PerceptionResult, StepStatus
from iris.contracts.appraisal import AppraisalSignal, AppraisalSignalKind, AppraisalSourceSpan
from iris.contracts.companion_affect import CompanionAffectStateKind
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.contracts.relationship import RelationshipSnapshotRecord
from iris.core.ids import AccountId, ActorId, ExternalRef, ObservationId, SessionId
from iris.runtime.state.ephemeral.relationship import InMemoryRelationshipStore

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
            appraisal_signals=classify_appraisal_signals(
                "thanks",
                source_observation_id=ObservationId("obs-relationship"),
            ),
        ),
    )


@pytest.mark.anyio
async def test_relationship_step_updates_actor_scoped_store() -> None:
    """RelationshipStep は ActorId ごとの関係性 state を更新する。"""
    actor = _actor()
    store = InMemoryRelationshipStore()

    result = await RelationshipStep(store).run(_positive_frame(actor))

    stored = await store.get(actor.actor_id)
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
    await store.upsert(
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
            appraisal_signals=classify_appraisal_signals(
                "thanks",
                source_observation_id=ObservationId("obs-relationship"),
            ),
        ),
    )

    result = await RelationshipStep(store).run(frame)

    assert result.status == StepStatus.OK
    assert result.actor_label == "Existing Mina"
    assert result.familiarity > 0.3


def _frame_with_text_and_appraisal(actor: Identity, text: str) -> WorkspaceFrame:
    builder = FrameBuilder()
    frame = builder.build_initial(_actor_message(actor))
    frame = builder.apply(
        frame,
        PerceptionResult(
            step_name="perception",
            status=StepStatus.OK,
            text=text,
        ),
    )
    return builder.apply(
        frame,
        AppraisalResult(
            step_name="appraisal",
            status=StepStatus.OK,
            mood_label="test",
            valence=-0.8,
            arousal=0.0,
            dominance=0.0,
            appraisal_signals=classify_appraisal_signals(
                text,
                source_observation_id=ObservationId("obs-relationship"),
            ),
        ),
    )


@pytest.mark.anyio
async def test_relationship_step_does_not_lower_trust_for_user_emotion() -> None:
    """「今日は悲しい」は user emotion であり trust / affinity 低下に使わない。"""
    actor = _actor()
    store = InMemoryRelationshipStore()

    result = await RelationshipStep(store, semantic_appraisal_mode=True).run(
        _frame_with_text_and_appraisal(actor, "今日は悲しい")
    )

    assert result.status == StepStatus.OK
    assert abs(result.affinity) <= 1e-12
    assert abs(result.trust - 0.5) <= 1e-12
    assert result.familiarity > 0.0


@pytest.mark.anyio
async def test_relationship_step_does_not_use_topic_sentiment_as_attitude() -> None:
    """Topic sentiment だけでは relationship を悪化させない。"""
    actor = _actor()
    store = InMemoryRelationshipStore()

    result = await RelationshipStep(store, semantic_appraisal_mode=True).run(
        _frame_with_text_and_appraisal(actor, "この映画は最悪"),
    )

    assert result.status == StepStatus.OK
    assert abs(result.affinity) <= 1e-12
    assert abs(result.trust - 0.5) <= 1e-12
    assert result.familiarity > 0.0


@pytest.mark.anyio
async def test_relationship_step_does_not_directly_apply_iris_attitude_before_policy_v2() -> None:
    """#102 の bounded policy までは attitude signal でも affinity/trust を直接更新しない。"""
    actor = _actor()
    store = InMemoryRelationshipStore()

    result = await RelationshipStep(store, semantic_appraisal_mode=True).run(
        _frame_with_text_and_appraisal(actor, "Irisが好き、ありがとう"),
    )

    assert result.status == StepStatus.OK
    assert abs(result.affinity) <= 1e-12
    assert abs(result.trust - 0.5) <= 1e-12
    assert result.familiarity > 0.0


@pytest.mark.anyio
async def test_relationship_step_semantic_mode_is_familiarity_only_for_all_signals() -> None:
    """Semantic mode は #100 では durable relationship valence を直接 mutate しない。"""
    actor = _actor()
    store = InMemoryRelationshipStore()

    result = await RelationshipStep(store, semantic_appraisal_mode=True).run(
        _frame_with_text_and_appraisal(actor, "Irisは役に立たない"),
    )

    assert result.status == StepStatus.OK
    assert abs(result.affinity) <= 1e-12
    assert abs(result.trust - 0.5) <= 1e-12
    assert result.familiarity > 0.0


@pytest.mark.anyio
async def test_relationship_step_treats_low_confidence_attitude_conservatively() -> None:
    """Low-confidence attitude signal も #102 までは familiarity-only に留める。"""
    actor = _actor()
    store = InMemoryRelationshipStore()
    low_confidence = AppraisalSignal(
        kind=AppraisalSignalKind.ATTITUDE_TOWARD_IRIS,
        label="positive_attitude",
        polarity=1.0,
        confidence=0.4,
        reason="test low confidence",
        source_span=AppraisalSourceSpan(start_index=0, end_index=5, text="Irisが"),
        state_boundary=CompanionAffectStateKind.ACTOR_RELATIONSHIP,
    )
    builder = FrameBuilder()
    frame = builder.build_initial(_actor_message(actor))
    frame = builder.apply(
        frame,
        PerceptionResult(
            step_name="perception",
            status=StepStatus.OK,
            text="Irisが好き",
        ),
    )
    frame = builder.apply(
        frame,
        AppraisalResult(
            step_name="appraisal",
            status=StepStatus.OK,
            mood_label="positive",
            valence=0.8,
            appraisal_signals=(low_confidence,),
        ),
    )

    result = await RelationshipStep(store, semantic_appraisal_mode=True).run(frame)

    assert result.status == StepStatus.OK
    assert abs(result.affinity) <= 1e-12
    assert abs(result.trust - 0.5) <= 1e-12
    assert result.familiarity > 0.0


@pytest.mark.anyio
async def test_relationship_step_can_use_legacy_vad_when_config_gate_disabled() -> None:
    """Runtime gate off の旧 VAD 経路は明示 opt-out として残す。"""
    actor = _actor()
    store = InMemoryRelationshipStore()

    result = await RelationshipStep(store, semantic_appraisal_mode=False).run(
        _positive_frame(actor)
    )

    assert result.status == StepStatus.OK
    assert result.affinity > 0.0
    assert result.trust > 0.5
