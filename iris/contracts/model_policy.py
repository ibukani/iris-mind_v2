"""モデル呼び出し予算と cascade policy の共有契約。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.metadata import ImmutableMetadata
from iris.core.metadata import immutable_metadata


class ModelCallKind(StrEnum):
    """Runtime が予算管理するモデル系呼び出し種別。"""

    LARGE_LLM = "large_llm"
    SMALL_CLASSIFIER = "small_classifier"
    EMBEDDING = "embedding"
    RERANKER = "reranker"
    BACKGROUND_LLM = "background_llm"


class ModelCallSite(StrEnum):
    """モデル呼び出しが発生した runtime / feature の場所。"""

    USER_RESPONSE_HOT_PATH = "user_response_hot_path"
    EVENT_REACTION = "event_reaction"
    PROACTIVE = "proactive"
    MEMORY_EXTRACTION = "memory_extraction"
    REFLECTION = "reflection"
    RELATIONSHIP_UPDATE = "relationship_update"
    INTERACTION_POLICY_CANDIDATE = "interaction_policy_candidate"
    RUNTIME_LEARNING_HOOK = "runtime_learning_hook"


class CascadeDecision(StrEnum):
    """Cascade policy の判定結果。"""

    ACCEPT = "accept"
    ESCALATE = "escalate"
    FALLBACK = "fallback"
    DEFER = "defer"
    DENY = "deny"


class CascadeFallbackBehavior(StrEnum):
    """上位モデルへ進めないときの安全な fallback 挙動。"""

    NO_OP = "no_op"
    DETERMINISTIC_BASELINE = "deterministic_baseline"
    DEFER = "defer"
    ENQUEUE_BACKGROUND = "enqueue_background"
    REJECT = "reject"


class ModelCallDescriptor(BaseModel):
    """予算判定に渡すモデル呼び出し要求の安全なメタデータ。"""

    model_config = ConfigDict(frozen=True)

    call_kind: ModelCallKind
    call_site: ModelCallSite
    model_slot: str | None = None
    model_name: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    high_risk: bool = False
    uncertain: bool = False
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class CascadeResult(BaseModel):
    """予算・信頼度・risk に基づく cascade 判定結果。"""

    model_config = ConfigDict(frozen=True)

    decision: CascadeDecision
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    fallback_behavior: CascadeFallbackBehavior | None = None
    model_metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)

    @property
    def accepted(self) -> bool:
        """通常の呼び出しを実行してよい場合に True。"""
        return self.decision is CascadeDecision.ACCEPT
