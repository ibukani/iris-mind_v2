"""永続 transcript の型付き契約。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from iris.contracts.metadata import ImmutableMetadata
from iris.core.ids import AccountId, ActorId, ObservationId, SessionId, SpaceId, TranscriptId


class TranscriptRole(StrEnum):
    """Transcript に保存する発話役割。"""

    USER = "user"
    ASSISTANT = "assistant"


class TranscriptSource(StrEnum):
    """Transcript record が確定した runtime 境界。"""

    INLINE_RESPONSE = "inline_response"
    DELIVERED_ACTION = "delivered_action"


class TranscriptSubjectKind(StrEnum):
    """Transcript を分離する主体種別。"""

    ACTOR = "actor"
    ACCOUNT = "account"
    SESSION = "session"


class TranscriptRetentionPolicy(BaseModel):
    """Transcript record の保持期限設定。"""

    model_config = ConfigDict(frozen=True)

    retention_days: int = 30


class TranscriptDeletionPolicy(BaseModel):
    """Transcript 削除時に他 state を巻き込まないための明示 policy。

    Transcript は raw conversation state であり、canonical memory や review
    candidate とは別 state として扱う。将来の管理 API はこの policy を
    明示的に拡張するまで、transcript 削除を他 state 削除へ伝搬しない。
    """

    model_config = ConfigDict(frozen=True)

    delete_transcript_records: bool = True
    delete_canonical_memory: bool = False
    delete_review_candidates: bool = False
    delete_delivery_state: bool = False


class TranscriptRecord(BaseModel):
    """MemoryStore とは分離された、確定済み会話 transcript の単一 record。"""

    model_config = ConfigDict(frozen=True)

    transcript_id: TranscriptId
    subject_kind: TranscriptSubjectKind
    subject_id: str
    role: TranscriptRole
    source: TranscriptSource
    content: str
    occurred_at: datetime
    recorded_at: datetime
    session_id: SessionId
    observation_id: ObservationId | None = None
    actor_id: ActorId | None = None
    account_id: AccountId | None = None
    space_id: SpaceId | None = None
    retention_until: datetime | None = None
    metadata: ImmutableMetadata = Field(default_factory=dict)


class TranscriptQuery(BaseModel):
    """TranscriptStore から record を取得するための境界付き query。"""

    model_config = ConfigDict(frozen=True)

    subject_kind: TranscriptSubjectKind | None = None
    subject_id: str | None = None
    actor_id: ActorId | None = None
    account_id: AccountId | None = None
    space_id: SpaceId | None = None
    session_id: SessionId | None = None
    occurred_after: datetime | None = None
    occurred_before: datetime | None = None
    after_occurred_at: datetime | None = None
    after_transcript_id: TranscriptId | None = None
    limit: int = Field(default=100, ge=0, le=1001)


class TranscriptAccessScope(BaseModel):
    """Transcript read を owner scope 内へ閉じる typed boundary。"""

    model_config = ConfigDict(frozen=True)

    actor_id: ActorId | None = None
    account_id: AccountId | None = None
    space_id: SpaceId | None = None
    session_id: SessionId | None = None

    @model_validator(mode="after")
    def _require_owner_scope(self) -> TranscriptAccessScope:
        """Actor / account / space のない broad query を拒否する。

        Returns:
            検証済みの access scope。

        Raises:
            ValueError: owner scope が一つもない場合。
        """
        if not any(value is not None for value in (self.actor_id, self.account_id, self.space_id)):
            message = "transcript access requires actor_id, account_id, or space_id"
            raise ValueError(message)
        return self


class TranscriptTimeRange(BaseModel):
    """Transcript query の bounded date range。"""

    model_config = ConfigDict(frozen=True)

    start: datetime | None = None
    end: datetime | None = None

    @model_validator(mode="after")
    def _validate_order(self) -> TranscriptTimeRange:
        """終了時刻が開始時刻より前にならないことを検証する。

        Returns:
            検証済みの time range。

        Raises:
            ValueError: end が start 以下の場合。
        """
        if self.start is not None and self.end is not None and self.end <= self.start:
            message = "transcript time range end must be after start"
            raise ValueError(message)
        return self


class TranscriptPageRequest(BaseModel):
    """Transcript read-only query の bounded page request。"""

    model_config = ConfigDict(frozen=True)

    scope: TranscriptAccessScope
    time_range: TranscriptTimeRange = Field(default_factory=TranscriptTimeRange)
    limit: int = Field(default=100, ge=1, le=100)
    cursor: str | None = Field(default=None, min_length=1)


class TranscriptPage(BaseModel):
    """Transcript query の read-only page response。"""

    model_config = ConfigDict(frozen=True)

    records: tuple[TranscriptRecord, ...]
    next_cursor: str | None = None


class TranscriptExportRequest(BaseModel):
    """Transcript export の bounded request。"""

    model_config = ConfigDict(frozen=True)

    scope: TranscriptAccessScope
    time_range: TranscriptTimeRange = Field(default_factory=TranscriptTimeRange)
    max_records: int = Field(default=1000, ge=1, le=1000)


class TranscriptExport(BaseModel):
    """Transcript export の bounded read-only response。"""

    model_config = ConfigDict(frozen=True)

    records: tuple[TranscriptRecord, ...]
    truncated: bool
    next_cursor: str | None = None


class TranscriptPruneResult(BaseModel):
    """Retention prune の結果。"""

    model_config = ConfigDict(frozen=True)

    deleted_count: int
