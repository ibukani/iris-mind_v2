"""永続 transcript の型付き契約。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

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
    limit: int = 100


class TranscriptPruneResult(BaseModel):
    """Retention prune の結果。"""

    model_config = ConfigDict(frozen=True)

    deleted_count: int
