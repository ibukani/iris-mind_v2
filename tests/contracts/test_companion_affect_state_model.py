"""Companion affect state model contract tests。"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError
import pytest

from iris.contracts.companion_affect import (
    COMPANION_AFFECT_STATE_BOUNDARIES,
    COMPANION_AFFECT_STATE_VOCABULARY,
    DIRECT_MESSAGE_STATE_BOUNDARY,
    GROUP_SPACE_STATE_BOUNDARY,
    ActorAffectTrace,
    ActorRelationshipState,
    CompanionAffectOwnerKind,
    CompanionAffectPersistence,
    CompanionAffectStateBoundary,
    CompanionAffectStateKind,
    CompanionInteractionScope,
    InteractionStateBoundary,
    IrisGlobalMoodState,
    RecentInteractionTone,
    SpaceAtmosphereState,
    companion_affect_state_boundary,
)
from iris.core.ids import AccountId, ActorId, SpaceId

EXPECTED_STATE_KINDS = {
    "iris_global_mood",
    "actor_relationship_state",
    "actor_affect_trace",
    "space_atmosphere_state",
    "recent_interaction_tone",
}


def test_state_vocabulary_names_are_stable_for_downstream_contracts() -> None:
    """#100 / #102 / #72 が参照する state vocabulary を固定する。"""
    assert {kind.value for kind in CompanionAffectStateKind} == EXPECTED_STATE_KINDS
    assert {boundary.kind for boundary in COMPANION_AFFECT_STATE_BOUNDARIES} == set(
        CompanionAffectStateKind
    )


def test_global_mood_and_actor_relationship_are_distinct_durable_targets() -> None:
    """Global mood と actor relationship を別 owner の durable state として固定する。"""
    global_mood = IrisGlobalMoodState(mood_label="calm", valence=0.2)
    relationship = ActorRelationshipState(actor_id=ActorId("actor-1"), affinity=0.4)

    global_boundary = companion_affect_state_boundary(CompanionAffectStateKind.IRIS_GLOBAL_MOOD)
    relationship_boundary = companion_affect_state_boundary(
        CompanionAffectStateKind.ACTOR_RELATIONSHIP
    )

    assert global_mood.owner_kind is CompanionAffectOwnerKind.IRIS
    assert relationship.owner_kind is CompanionAffectOwnerKind.ACTOR
    assert global_boundary.persistence is CompanionAffectPersistence.DURABLE
    assert relationship_boundary.persistence is CompanionAffectPersistence.DURABLE
    assert global_boundary.kind is not relationship_boundary.kind
    assert relationship_boundary.relationship_policy_target is True


def test_actor_relationship_can_carry_account_scope_without_becoming_account_owned() -> None:
    """Account scope は補助参照であり durable relationship owner は Actor のままにする。"""
    relationship = ActorRelationshipState(
        actor_id=ActorId("actor-1"),
        account_id=AccountId("account-1"),
        trust=0.8,
    )

    boundary = companion_affect_state_boundary(CompanionAffectStateKind.ACTOR_RELATIONSHIP)

    assert relationship.account_id == AccountId("account-1")
    assert relationship.owner_kind is CompanionAffectOwnerKind.ACTOR
    assert boundary.owner_kind is CompanionAffectOwnerKind.ACTOR
    assert CompanionAffectOwnerKind.ACCOUNT.value == "account"


def test_actor_affect_trace_is_not_relationship_state() -> None:
    """Actor affect trace を relationship update target と混ぜない。"""
    trace = ActorAffectTrace(
        actor_id=ActorId("actor-1"),
        emotion_label="sad",
        observed_valence=-0.7,
        confidence=0.8,
    )
    trace_boundary = companion_affect_state_boundary(CompanionAffectStateKind.ACTOR_AFFECT_TRACE)

    assert trace.owner_kind is CompanionAffectOwnerKind.ACTOR
    assert trace.persistence is CompanionAffectPersistence.DERIVED
    assert trace_boundary.relationship_policy_target is False
    assert trace_boundary.durable_update_target is False


def test_space_atmosphere_is_not_durable_user_memory_owner() -> None:
    """Space atmosphere は group-space context に閉じた derived state にする。"""
    atmosphere = SpaceAtmosphereState(
        space_id=SpaceId("space-1"),
        atmosphere_label="tense",
        arousal=0.6,
        confidence=0.7,
    )
    boundary = companion_affect_state_boundary(CompanionAffectStateKind.SPACE_ATMOSPHERE)

    assert atmosphere.owner_kind is CompanionAffectOwnerKind.SPACE
    assert atmosphere.persistence is CompanionAffectPersistence.DERIVED
    assert boundary.durable_update_target is False
    assert boundary.worker_candidate_target is False


def test_recent_interaction_tone_is_ephemeral_not_durable_memory() -> None:
    """Recent interaction tone を durable memory / relationship として扱わない。"""
    tone = RecentInteractionTone(
        tone_label="playful",
        actor_id=ActorId("actor-1"),
        valence=0.5,
        confidence=0.9,
    )
    boundary = companion_affect_state_boundary(
        CompanionAffectStateKind.RECENT_INTERACTION_TONE
    )

    assert tone.persistence is CompanionAffectPersistence.EPHEMERAL
    assert boundary.durable_update_target is False
    assert boundary.relationship_policy_target is False
    assert boundary.worker_candidate_target is False


def test_group_space_atmosphere_does_not_leak_into_dm_relationship() -> None:
    """Group-space atmosphere を DM relationship の durable update source にしない。"""
    assert DIRECT_MESSAGE_STATE_BOUNDARY.scope is CompanionInteractionScope.DIRECT_MESSAGE
    assert DIRECT_MESSAGE_STATE_BOUNDARY.may_read_space_atmosphere is False
    assert CompanionAffectStateKind.SPACE_ATMOSPHERE in (
        DIRECT_MESSAGE_STATE_BOUNDARY.forbidden_durable_update_sources
    )
    assert GROUP_SPACE_STATE_BOUNDARY.scope is CompanionInteractionScope.GROUP_SPACE
    assert GROUP_SPACE_STATE_BOUNDARY.may_read_space_atmosphere is True
    assert CompanionAffectStateKind.SPACE_ATMOSPHERE in (
        GROUP_SPACE_STATE_BOUNDARY.forbidden_durable_update_sources
    )
    assert GROUP_SPACE_STATE_BOUNDARY.relationship_owner_kind is CompanionAffectOwnerKind.ACTOR


def test_state_model_exposes_appraisal_relationship_and_worker_boundaries() -> None:
    """#100 / #102 / #72 が参照する境界を vocabulary から取得できる。"""
    vocabulary = COMPANION_AFFECT_STATE_VOCABULARY

    assert CompanionAffectStateKind.ACTOR_AFFECT_TRACE in vocabulary.appraisal_readable_state_kinds
    assert CompanionAffectStateKind.SPACE_ATMOSPHERE in vocabulary.appraisal_readable_state_kinds
    assert vocabulary.relationship_update_target_kinds == (
        CompanionAffectStateKind.ACTOR_RELATIONSHIP,
    )
    assert vocabulary.worker_candidate_target_kinds == (
        CompanionAffectStateKind.IRIS_GLOBAL_MOOD,
        CompanionAffectStateKind.ACTOR_RELATIONSHIP,
    )
    assert vocabulary.production_ordering_required_state_kinds == (
        CompanionAffectStateKind.IRIS_GLOBAL_MOOD,
        CompanionAffectStateKind.ACTOR_RELATIONSHIP,
    )


def test_worker_targets_require_candidate_update_not_direct_mutation() -> None:
    """#72 worker の durable target は direct mutation ではなく candidate update に限定する。"""
    for kind in COMPANION_AFFECT_STATE_VOCABULARY.worker_candidate_target_kinds:
        boundary = companion_affect_state_boundary(kind)

        assert boundary.durable_update_target is True
        assert boundary.requires_candidate_update is True
        assert boundary.production_ordering_required_for_durable_update is True


def test_production_ordering_gate_applies_only_to_durable_update_targets() -> None:
    """#74 ordering gate を non-durable state に付けられない。"""
    with pytest.raises(ValidationError):
        CompanionAffectStateBoundary(
            kind=CompanionAffectStateKind.SPACE_ATMOSPHERE,
            owner_kind=CompanionAffectOwnerKind.SPACE,
            persistence=CompanionAffectPersistence.DERIVED,
            prompt_summary_allowed=True,
            appraisal_readable=True,
            production_ordering_required_for_durable_update=True,
            notes="invalid",
        )


def test_boundary_rejects_non_durable_direct_update_target() -> None:
    """Ephemeral / derived state を durable update target にできない。"""
    with pytest.raises(ValidationError):
        CompanionAffectStateBoundary(
            kind=CompanionAffectStateKind.RECENT_INTERACTION_TONE,
            owner_kind=CompanionAffectOwnerKind.INTERACTION,
            persistence=CompanionAffectPersistence.EPHEMERAL,
            prompt_summary_allowed=True,
            appraisal_readable=True,
            durable_update_target=True,
            notes="invalid",
        )


def test_interaction_boundary_requires_recent_tone_as_forbidden_update_source() -> None:
    """Recent interaction tone を durable update source から必ず除外する。"""
    with pytest.raises(ValidationError):
        InteractionStateBoundary(
            scope=CompanionInteractionScope.DIRECT_MESSAGE,
            may_read_space_atmosphere=False,
            allowed_durable_update_targets=(CompanionAffectStateKind.ACTOR_RELATIONSHIP,),
            forbidden_durable_update_sources=(),
            notes="invalid",
        )


def test_state_models_reject_blank_owner_ids() -> None:
    """Actor / Space owner は空 ID にできない。"""
    with pytest.raises(ValidationError):
        ActorRelationshipState(actor_id=ActorId(""))
    with pytest.raises(ValidationError):
        ActorRelationshipState(actor_id=ActorId("actor-1"), account_id=AccountId(""))
    with pytest.raises(ValidationError):
        ActorAffectTrace(actor_id=ActorId(""))
    with pytest.raises(ValidationError):
        SpaceAtmosphereState(space_id=SpaceId(""))


def test_companion_affect_state_adr_documents_required_boundaries() -> None:
    """ADR 0016 に Issue #104 の主要境界を固定する。"""
    adr = Path("docs/adr/0016-companion-affect-state-model.md").read_text(encoding="utf-8")

    for token in (
        "IrisGlobalMood",
        "ActorRelationshipState",
        "ActorAffectTrace",
        "SpaceAtmosphereState",
        "RecentInteractionTone",
        "durable",
        "ephemeral",
        "derived",
        "#100",
        "#102",
        "#72",
        "#74",
    ):
        assert token in adr
