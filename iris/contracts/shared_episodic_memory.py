"""共有エピソード記憶候補の型付き契約。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from iris.contracts.metadata import ImmutableMetadata
from iris.core.ids import AccountId, ActorId, ObservationId, SpaceId
from iris.core.metadata import immutable_metadata


class SharedEpisodicMemoryKind(StrEnum):
    """AIコンパニオン向け共有エピソード記憶の候補種別。"""

    SHARED_EVENT = "shared_event"
    RUNNING_JOKE = "running_joke"
    COMPANION_MILESTONE = "companion_milestone"
    HELP_EXCHANGE = "user_helped_iris_or_iris_helped_user"
    CONFLICT_AND_REPAIR = "conflict_and_repair"
    MEMORABLE_FAILURE_OR_TEASING = "memorable_failure_or_teasing"
    RECURRING_TOPIC_WITH_EMOTION = "recurring_topic_with_emotion"


class SharedEpisodicAdmissionRisk(StrEnum):
    """共有エピソード候補に含まれる機微性・羞恥リスク。"""

    NORMAL = "normal"
    PRIVATE = "private"
    SENSITIVE = "sensitive"
    EMBARRASSING = "embarrassing"
    SECRET_LIKE = "secret" + "_like"


class SharedEpisodicAdmissionPolicy(StrEnum):
    """共有エピソード候補を review 境界へ入れるかどうかの初期方針。"""

    REVIEW_REQUIRED = "review_required"
    REJECT = "reject"


class SharedEpisodicSourceEventRef(BaseModel):
    """共有エピソード候補の根拠となった source event 参照。"""

    model_config = ConfigDict(frozen=True)

    source_event_id: str = Field(min_length=1)
    observation_id: ObservationId
    occurred_at: datetime

    @field_validator("source_event_id")
    @classmethod
    def _source_event_id_must_not_be_blank(cls, value: str) -> str:
        """空白だけの source event ID を拒否する。

        Returns:
            検証済み source event ID。

        Raises:
            ValueError: source event ID が空白だけの場合。
        """
        if not value.strip():
            message = "source_event_id must not be blank"
            raise ValueError(message)
        return value


class SharedEpisodicRetrievalMetadata(BaseModel):
    """#94 retrieval / reranking が参照できる軽量 metadata。"""

    model_config = ConfigDict(frozen=True)

    topics: tuple[str, ...] = ()
    emotional_context: str | None = None
    relationship_signal: str | None = None
    salience: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("topics")
    @classmethod
    def _topics_must_not_contain_blank(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """空白だけの検索 topic を拒否する。

        Returns:
            検証済み topic tuple。

        Raises:
            ValueError: 空白だけの topic が含まれる場合。
        """
        if any(not topic.strip() for topic in value):
            message = "retrieval topics must not contain blank values"
            raise ValueError(message)
        return value


class SharedEpisodicMemoryCandidate(BaseModel):
    """Review 境界に入る前の共有エピソード記憶候補。"""

    model_config = ConfigDict(frozen=True)

    summary: str = Field(min_length=1)
    kind: SharedEpisodicMemoryKind
    actor_id: ActorId
    account_id: AccountId
    space_id: SpaceId
    source_events: tuple[SharedEpisodicSourceEventRef, ...] = Field(min_length=1)
    occurred_at: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    review_required: bool = True
    admission_policy: SharedEpisodicAdmissionPolicy = SharedEpisodicAdmissionPolicy.REVIEW_REQUIRED
    admission_risk: SharedEpisodicAdmissionRisk = SharedEpisodicAdmissionRisk.NORMAL
    retrieval: SharedEpisodicRetrievalMetadata = Field(
        default_factory=SharedEpisodicRetrievalMetadata
    )
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)

    @field_validator("summary", "reason")
    @classmethod
    def _text_fields_must_not_be_blank(cls, value: str) -> str:
        """空白だけの説明文を拒否する。

        Returns:
            検証済み文字列。

        Raises:
            ValueError: 空白だけの文字列の場合。
        """
        if not value.strip():
            message = "shared episodic memory text fields must not be blank"
            raise ValueError(message)
        return value

    @model_validator(mode="after")
    def _validate_admission_policy(self) -> SharedEpisodicMemoryCandidate:
        """Review-required 既定と secret-like rejection を強制する。

        Returns:
            検証済み候補。

        Raises:
            ValueError: admission policy が安全でない場合。
        """
        _require_non_empty_id(str(self.actor_id), "actor_id")
        _require_non_empty_id(str(self.account_id), "account_id")
        _require_non_empty_id(str(self.space_id), "space_id")
        if (
            self.admission_policy is SharedEpisodicAdmissionPolicy.REVIEW_REQUIRED
            and not self.review_required
        ):
            message = "review_required must be true when admission policy is review_required"
            raise ValueError(message)
        if self.admission_policy is SharedEpisodicAdmissionPolicy.REJECT and self.review_required:
            message = "review_required must be false when admission policy is reject"
            raise ValueError(message)
        if (
            self.admission_risk is SharedEpisodicAdmissionRisk.SECRET_LIKE
            and self.admission_policy is not SharedEpisodicAdmissionPolicy.REJECT
        ):
            message = "secret-like shared episodic memories must be rejected"
            raise ValueError(message)
        return self


def _require_non_empty_id(value: str, field_name: str) -> None:
    """NewType ID の空文字を拒否する。

    Raises:
        ValueError: ID が空文字の場合。
    """
    if not value:
        message = f"{field_name} must not be blank"
        raise ValueError(message)
