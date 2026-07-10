"""AIコンパニオン向け affect state boundary の型付き契約。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from iris.contracts.validation import require_non_empty_id
from iris.core.ids import AccountId, ActorId, ObservationId, SpaceId


class CompanionAffectStateKind(StrEnum):
    """Companion affect model で扱う状態種別。"""

    IRIS_GLOBAL_MOOD = "iris_global_mood"
    ACTOR_RELATIONSHIP = "actor_relationship_state"
    ACTOR_AFFECT_TRACE = "actor_affect_trace"
    SPACE_ATMOSPHERE = "space_atmosphere_state"
    RECENT_INTERACTION_TONE = "recent_interaction_tone"


class CompanionAffectPersistence(StrEnum):
    """Companion affect state の永続化分類。"""

    DURABLE = "durable"
    EPHEMERAL = "ephemeral"
    DERIVED = "derived"


class CompanionAffectOwnerKind(StrEnum):
    """Companion affect state の owner 境界。"""

    IRIS = "iris"
    ACTOR = "actor"
    ACCOUNT = "account"
    SPACE = "space"
    INTERACTION = "interaction"


class CompanionInteractionScope(StrEnum):
    """状態境界を切り替える interaction scope。"""

    DIRECT_MESSAGE = "direct_message"
    GROUP_SPACE = "group_space"


class CompanionAffectStateBoundary(BaseModel):
    """各 companion affect state の owner / persistence / update 境界。"""

    model_config = ConfigDict(frozen=True)

    kind: CompanionAffectStateKind
    owner_kind: CompanionAffectOwnerKind
    persistence: CompanionAffectPersistence
    prompt_summary_allowed: bool
    appraisal_readable: bool
    durable_update_target: bool = False
    relationship_policy_target: bool = False
    worker_candidate_target: bool = False
    requires_candidate_update: bool = False
    production_ordering_required_for_durable_update: bool = False
    notes: str

    @model_validator(mode="after")
    def _validate_boundary(self) -> CompanionAffectStateBoundary:
        """Durable update と candidate update の不変条件を検証する。

        Returns:
            検証済み境界。

        Raises:
            ValueError: state boundary が安全でない場合。
        """
        if (
            self.durable_update_target
            and self.persistence is not CompanionAffectPersistence.DURABLE
        ):
            message = "durable update targets must be durable state"
            raise ValueError(message)
        if self.requires_candidate_update and not self.durable_update_target:
            message = "candidate update gate requires a durable update target"
            raise ValueError(message)
        if (
            self.relationship_policy_target
            and self.kind is not CompanionAffectStateKind.ACTOR_RELATIONSHIP
        ):
            message = "relationship policy may directly target only actor relationship state"
            raise ValueError(message)
        if self.worker_candidate_target and not self.requires_candidate_update:
            message = "worker candidate targets must require candidate update"
            raise ValueError(message)
        if self.production_ordering_required_for_durable_update and not self.durable_update_target:
            message = "production ordering gate is meaningful only for durable update targets"
            raise ValueError(message)
        return self


class InteractionStateBoundary(BaseModel):
    """DM / group-space ごとの cross-scope leak 防止境界。"""

    model_config = ConfigDict(frozen=True)

    scope: CompanionInteractionScope
    may_read_space_atmosphere: bool
    allowed_durable_update_targets: tuple[CompanionAffectStateKind, ...]
    forbidden_durable_update_sources: tuple[CompanionAffectStateKind, ...]
    relationship_owner_kind: CompanionAffectOwnerKind = CompanionAffectOwnerKind.ACTOR
    notes: str

    @model_validator(mode="after")
    def _validate_interaction_boundary(self) -> InteractionStateBoundary:
        """短期 tone と group atmosphere が durable update source にならないことを検証する。

        Returns:
            検証済み interaction boundary。

        Raises:
            ValueError: cross-scope leak を許す境界の場合。
        """
        if CompanionAffectStateKind.RECENT_INTERACTION_TONE not in (
            self.forbidden_durable_update_sources
        ):
            message = "recent interaction tone must not become a durable update source"
            raise ValueError(message)
        if (
            self.scope is CompanionInteractionScope.GROUP_SPACE
            and CompanionAffectStateKind.SPACE_ATMOSPHERE
            not in self.forbidden_durable_update_sources
        ):
            message = "group-space atmosphere must not directly drive durable updates"
            raise ValueError(message)
        return self


class IrisGlobalMoodState(BaseModel):
    """Iris 全体に属する durable global mood state。"""

    model_config = ConfigDict(frozen=True)

    kind: Literal[CompanionAffectStateKind.IRIS_GLOBAL_MOOD] = (
        CompanionAffectStateKind.IRIS_GLOBAL_MOOD
    )
    owner_kind: Literal[CompanionAffectOwnerKind.IRIS] = CompanionAffectOwnerKind.IRIS
    persistence: Literal[CompanionAffectPersistence.DURABLE] = CompanionAffectPersistence.DURABLE
    mood_label: str | None = None
    valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    arousal: float = Field(default=0.0, ge=-1.0, le=1.0)
    dominance: float = Field(default=0.0, ge=-1.0, le=1.0)
    summary: str | None = None
    source_observation_id: ObservationId | None = None
    updated_at: datetime | None = None
    version: int = Field(default=1, ge=1)


class ActorRelationshipState(BaseModel):
    """Actor を owner とする durable relationship state。"""

    model_config = ConfigDict(frozen=True)

    kind: Literal[CompanionAffectStateKind.ACTOR_RELATIONSHIP] = (
        CompanionAffectStateKind.ACTOR_RELATIONSHIP
    )
    owner_kind: Literal[CompanionAffectOwnerKind.ACTOR] = CompanionAffectOwnerKind.ACTOR
    persistence: Literal[CompanionAffectPersistence.DURABLE] = CompanionAffectPersistence.DURABLE
    actor_id: ActorId
    account_id: AccountId | None = None
    affinity: float = Field(default=0.0, ge=-1.0, le=1.0)
    trust: float = Field(default=0.5, ge=0.0, le=1.0)
    familiarity: float = Field(default=0.0, ge=0.0, le=1.0)
    summary: str | None = None
    source_observation_id: ObservationId | None = None
    updated_at: datetime | None = None
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _validate_actor_owner(self) -> ActorRelationshipState:
        """Actor owner と account 補助 scope が空 ID で失われないことを検証する。

        Returns:
            検証済み relationship state。
        """
        require_non_empty_id(str(self.actor_id), "actor_id")
        if self.account_id is not None:
            require_non_empty_id(str(self.account_id), "account_id")
        return self


class ActorAffectTrace(BaseModel):
    """Actor から観測された recent affect trace。"""

    model_config = ConfigDict(frozen=True)

    kind: Literal[CompanionAffectStateKind.ACTOR_AFFECT_TRACE] = (
        CompanionAffectStateKind.ACTOR_AFFECT_TRACE
    )
    owner_kind: Literal[CompanionAffectOwnerKind.ACTOR] = CompanionAffectOwnerKind.ACTOR
    persistence: Literal[CompanionAffectPersistence.DERIVED] = CompanionAffectPersistence.DERIVED
    actor_id: ActorId
    emotion_label: str | None = None
    observed_valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    observed_arousal: float = Field(default=0.0, ge=-1.0, le=1.0)
    observed_dominance: float = Field(default=0.0, ge=-1.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_observation_id: ObservationId | None = None
    observed_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_actor_owner(self) -> ActorAffectTrace:
        """Actor owner が空 ID で失われないことを検証する。

        Returns:
            検証済み actor affect trace。
        """
        require_non_empty_id(str(self.actor_id), "actor_id")
        return self


class SpaceAtmosphereState(BaseModel):
    """Space に閉じた derived atmosphere state。"""

    model_config = ConfigDict(frozen=True)

    kind: Literal[CompanionAffectStateKind.SPACE_ATMOSPHERE] = (
        CompanionAffectStateKind.SPACE_ATMOSPHERE
    )
    owner_kind: Literal[CompanionAffectOwnerKind.SPACE] = CompanionAffectOwnerKind.SPACE
    persistence: Literal[CompanionAffectPersistence.DERIVED] = CompanionAffectPersistence.DERIVED
    space_id: SpaceId
    atmosphere_label: str | None = None
    valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    arousal: float = Field(default=0.0, ge=-1.0, le=1.0)
    dominance: float = Field(default=0.0, ge=-1.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_observation_id: ObservationId | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_space_owner(self) -> SpaceAtmosphereState:
        """Space owner が空 ID で失われないことを検証する。

        Returns:
            検証済み space atmosphere state。
        """
        require_non_empty_id(str(self.space_id), "space_id")
        return self


class RecentInteractionTone(BaseModel):
    """1 ターンまたは短期 window に閉じた ephemeral interaction tone。"""

    model_config = ConfigDict(frozen=True)

    kind: Literal[CompanionAffectStateKind.RECENT_INTERACTION_TONE] = (
        CompanionAffectStateKind.RECENT_INTERACTION_TONE
    )
    owner_kind: Literal[CompanionAffectOwnerKind.INTERACTION] = CompanionAffectOwnerKind.INTERACTION
    persistence: Literal[CompanionAffectPersistence.EPHEMERAL] = (
        CompanionAffectPersistence.EPHEMERAL
    )
    tone_label: str | None = None
    actor_id: ActorId | None = None
    space_id: SpaceId | None = None
    valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    arousal: float = Field(default=0.0, ge=-1.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_observation_id: ObservationId | None = None
    observed_at: datetime | None = None


class CompanionAffectStateVocabulary(BaseModel):
    """#100 / #102 / #72 が参照する companion affect state vocabulary。"""

    model_config = ConfigDict(frozen=True)

    state_boundaries: tuple[CompanionAffectStateBoundary, ...]
    direct_message_boundary: InteractionStateBoundary
    group_space_boundary: InteractionStateBoundary

    @property
    def appraisal_readable_state_kinds(self) -> tuple[CompanionAffectStateKind, ...]:
        """#100 appraisal signals が参照できる state kind を返す。"""
        return tuple(
            boundary.kind for boundary in self.state_boundaries if boundary.appraisal_readable
        )

    @property
    def relationship_update_target_kinds(self) -> tuple[CompanionAffectStateKind, ...]:
        """#102 relationship update policy が更新対象にできる state kind を返す。"""
        return tuple(
            boundary.kind
            for boundary in self.state_boundaries
            if boundary.relationship_policy_target
        )

    @property
    def worker_candidate_target_kinds(self) -> tuple[CompanionAffectStateKind, ...]:
        """#72 worker が candidate update として扱える state kind を返す。"""
        return tuple(
            boundary.kind for boundary in self.state_boundaries if boundary.worker_candidate_target
        )

    @property
    def production_ordering_required_state_kinds(self) -> tuple[CompanionAffectStateKind, ...]:
        """#74 ordering gate が必要な production-like durable update target を返す。"""
        return tuple(
            boundary.kind
            for boundary in self.state_boundaries
            if boundary.production_ordering_required_for_durable_update
        )


COMPANION_AFFECT_STATE_BOUNDARIES: tuple[CompanionAffectStateBoundary, ...] = (
    CompanionAffectStateBoundary(
        kind=CompanionAffectStateKind.IRIS_GLOBAL_MOOD,
        owner_kind=CompanionAffectOwnerKind.IRIS,
        persistence=CompanionAffectPersistence.DURABLE,
        prompt_summary_allowed=True,
        appraisal_readable=True,
        durable_update_target=True,
        worker_candidate_target=True,
        requires_candidate_update=True,
        production_ordering_required_for_durable_update=True,
        notes="Iris global mood baseline. It is not owned by actor, account, or space.",
    ),
    CompanionAffectStateBoundary(
        kind=CompanionAffectStateKind.ACTOR_RELATIONSHIP,
        owner_kind=CompanionAffectOwnerKind.ACTOR,
        persistence=CompanionAffectPersistence.DURABLE,
        prompt_summary_allowed=True,
        appraisal_readable=True,
        durable_update_target=True,
        relationship_policy_target=True,
        worker_candidate_target=True,
        requires_candidate_update=True,
        production_ordering_required_for_durable_update=True,
        notes="Per-actor relationship state updated only through bounded candidates.",
    ),
    CompanionAffectStateBoundary(
        kind=CompanionAffectStateKind.ACTOR_AFFECT_TRACE,
        owner_kind=CompanionAffectOwnerKind.ACTOR,
        persistence=CompanionAffectPersistence.DERIVED,
        prompt_summary_allowed=True,
        appraisal_readable=True,
        notes="Recent observed actor affect. It is not relationship state.",
    ),
    CompanionAffectStateBoundary(
        kind=CompanionAffectStateKind.SPACE_ATMOSPHERE,
        owner_kind=CompanionAffectOwnerKind.SPACE,
        persistence=CompanionAffectPersistence.DERIVED,
        prompt_summary_allowed=True,
        appraisal_readable=True,
        notes="Current group-space atmosphere. It is not durable user memory owner.",
    ),
    CompanionAffectStateBoundary(
        kind=CompanionAffectStateKind.RECENT_INTERACTION_TONE,
        owner_kind=CompanionAffectOwnerKind.INTERACTION,
        persistence=CompanionAffectPersistence.EPHEMERAL,
        prompt_summary_allowed=True,
        appraisal_readable=True,
        notes="Short-term interaction tone. It must not be stored as durable memory.",
    ),
)

DIRECT_MESSAGE_STATE_BOUNDARY = InteractionStateBoundary(
    scope=CompanionInteractionScope.DIRECT_MESSAGE,
    may_read_space_atmosphere=False,
    allowed_durable_update_targets=(
        CompanionAffectStateKind.IRIS_GLOBAL_MOOD,
        CompanionAffectStateKind.ACTOR_RELATIONSHIP,
    ),
    forbidden_durable_update_sources=(
        CompanionAffectStateKind.SPACE_ATMOSPHERE,
        CompanionAffectStateKind.RECENT_INTERACTION_TONE,
    ),
    notes="DM state uses the current actor boundary and does not import group atmosphere.",
)

GROUP_SPACE_STATE_BOUNDARY = InteractionStateBoundary(
    scope=CompanionInteractionScope.GROUP_SPACE,
    may_read_space_atmosphere=True,
    allowed_durable_update_targets=(
        CompanionAffectStateKind.IRIS_GLOBAL_MOOD,
        CompanionAffectStateKind.ACTOR_RELATIONSHIP,
    ),
    forbidden_durable_update_sources=(
        CompanionAffectStateKind.SPACE_ATMOSPHERE,
        CompanionAffectStateKind.RECENT_INTERACTION_TONE,
    ),
    notes="Group atmosphere may inform local tone but must not directly update durable state.",
)

COMPANION_AFFECT_STATE_VOCABULARY = CompanionAffectStateVocabulary(
    state_boundaries=COMPANION_AFFECT_STATE_BOUNDARIES,
    direct_message_boundary=DIRECT_MESSAGE_STATE_BOUNDARY,
    group_space_boundary=GROUP_SPACE_STATE_BOUNDARY,
)


def companion_affect_state_boundary(
    kind: CompanionAffectStateKind,
) -> CompanionAffectStateBoundary:
    """State kind から companion affect state boundary を取得する。

    Args:
        kind: 検索する state kind。

    Returns:
        対応する companion affect state boundary。

    Raises:
        ValueError: 未知の state kind の場合。
    """
    for boundary in COMPANION_AFFECT_STATE_BOUNDARIES:
        if boundary.kind is kind:
            return boundary
    message = f"unknown companion affect state kind: {kind}"
    raise ValueError(message)
