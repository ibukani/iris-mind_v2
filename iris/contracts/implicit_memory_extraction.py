"""暗黙メモリ抽出 worker と provider の typed contract。"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from iris.contracts.memory import MemoryKind
from iris.contracts.memory_candidates import MemoryCandidateSensitivity
from iris.contracts.metadata import ImmutableMetadata
from iris.core.ids import AccountId, ActorId, ObservationId, SpaceId
from iris.core.metadata import immutable_metadata


class ImplicitMemoryExtractionFailureKind(StrEnum):
    """暗黙メモリ抽出が候補を返せない理由。"""

    INVALID_OUTPUT = "invalid_output"
    PROVIDER_ERROR = "provider_error"
    BUDGET_DENIED = "budget_denied"
    CANCELLED = "cancelled"
    HIGH_RISK_SUPPRESSED = "high_risk_suppressed"


class ImplicitMemoryExtractionFailure(BaseModel):
    """LLM 抽出失敗を review/candidate pipeline で扱う typed 値。"""

    model_config = ConfigDict(frozen=True)

    kind: ImplicitMemoryExtractionFailureKind
    reason: str = Field(min_length=1, max_length=500)
    model_metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class ImplicitMemoryExtractionLimits(BaseModel):
    """抽出 prompt と provider response の上限。"""

    model_config = ConfigDict(frozen=True)

    max_input_chars: int = Field(default=4000, gt=0)
    max_output_tokens: int = Field(default=512, gt=0)


class ImplicitMemoryExtractionCancellation(Protocol):
    """Provider adapter が協調停止を観測するための最小契約。"""

    @property
    def cancellation_requested(self) -> bool:
        """停止要求が発行済みなら True。"""
        ...

    def acknowledge_stopped(self) -> None:
        """Provider call が停止したことを通知する。"""
        ...


class ImplicitMemoryExtractionRequest(BaseModel):
    """LLM 抽出へ渡す bounded な runtime event 入力。"""

    model_config = ConfigDict(frozen=True)

    input_text: str | None = None
    output_text: str | None = None
    source_observation_id: ObservationId
    source_event_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    actor_id: ActorId | None = None
    account_id: AccountId | None = None
    space_id: SpaceId | None = None
    model_name: str = Field(min_length=1, max_length=200)
    limits: ImplicitMemoryExtractionLimits = Field(default_factory=ImplicitMemoryExtractionLimits)

    @field_validator("source_event_ids")
    @classmethod
    def _event_ids_must_be_non_blank(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not event_id.strip() for event_id in value):
            message = "source event ids must not be blank"
            raise ValueError(message)
        return value


class ImplicitMemoryExtractionClient(Protocol):
    """LLM provider adapter を隠蔽する同期 extraction port。"""

    def extract(
        self,
        request: ImplicitMemoryExtractionRequest,
        *,
        cancellation: ImplicitMemoryExtractionCancellation | None = None,
    ) -> ImplicitMemoryExtractionResult:
        """Bounded request を typed result へ変換する。"""
        ...


class ImplicitMemoryExtractionCandidate(BaseModel):
    """LLM が返す、まだ durable でないメモリ候補。"""

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1, max_length=1000)
    kind: MemoryKind
    salience: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)
    source_event_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    sensitivity: MemoryCandidateSensitivity = MemoryCandidateSensitivity.NORMAL
    high_risk: bool = False
    actor_id: ActorId | None = None
    account_id: AccountId | None = None
    space_id: SpaceId | None = None
    model_metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)

    @field_validator("text", "reason")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value.strip():
            message = "implicit extraction text fields must not be blank"
            raise ValueError(message)
        return value

    @field_validator("source_event_ids")
    @classmethod
    def _event_ids_must_be_non_blank(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not event_id.strip() for event_id in value):
            message = "source event ids must not be blank"
            raise ValueError(message)
        return value


class ImplicitMemoryExtractionResult(BaseModel):
    """LLM 抽出結果。候補は最大三件で、durable memory には直接書き込まない。"""

    model_config = ConfigDict(frozen=True)

    candidates: tuple[ImplicitMemoryExtractionCandidate, ...] = Field(default=(), max_length=3)
    failure: ImplicitMemoryExtractionFailure | None = None
    model_metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)
