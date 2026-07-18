"""Runtime-owned ordering key と conflict decision の typed contract。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

from iris.core.ids import AccountId, ActorId, SessionId, SpaceId


class RuntimeOrderingKeyKind(StrEnum):
    """順序保証を分離する runtime-owned entity 種別。"""

    OBSERVATION = "observation"
    TRANSCRIPT = "transcript"
    INTERACTION_ACTIVITY = "interaction_activity"
    STATE_CANDIDATE = "state_candidate"
    DELIVERY_RESULT = "delivery_result"


class RuntimeOrderingKey(BaseModel):
    """同一 key だけを直列化するための scoped ordering key。"""

    model_config = ConfigDict(frozen=True)

    kind: RuntimeOrderingKeyKind
    adapter_id: str | None = None
    provider: str | None = None
    account_id: AccountId | None = None
    actor_id: ActorId | None = None
    space_id: SpaceId | None = None
    session_id: SessionId | None = None
    channel: str | None = None


class OrderingConflictReason(StrEnum):
    """順序・重複・version conflict の typed reason。"""

    DUPLICATE = "duplicate"
    STALE = "stale"
    VERSION_CONFLICT = "version_conflict"
    SCOPE_CONFLICT = "scope_conflict"
    BACKEND_UNAVAILABLE = "backend_unavailable"


class OrderingDecisionKind(StrEnum):
    """ordering decision の外部観測可能な結果。"""

    ACCEPT = "accept"
    IGNORE_DUPLICATE = "ignore_duplicate"
    IGNORE_STALE = "ignore_stale"
    REJECT_CONFLICT = "reject_conflict"
    DEFER = "defer"


class OrderingConflict(BaseModel):
    """conflict reason と比較した version を保持する。"""

    model_config = ConfigDict(frozen=True)

    reason: OrderingConflictReason
    expected_version: str | None = None
    observed_version: str | None = None


class OrderingDecision(BaseModel):
    """同一 ordering key に対する deterministic decision。"""

    model_config = ConfigDict(frozen=True)

    key: RuntimeOrderingKey
    decision: OrderingDecisionKind
    conflict: OrderingConflict | None = None

    @property
    def accepted(self) -> bool:
        """Mutation が受理され、後続 projection を進めてよい場合に True。

        Returns:
            ACCEPT decisionならTrue、それ以外ならFalse。
        """
        return self.decision is OrderingDecisionKind.ACCEPT

    @model_validator(mode="after")
    def _validate_conflict_presence(self) -> OrderingDecision:
        """Decision と conflict metadata の組み合わせを検証する。

        Returns:
            検証済みのordering decision。

        Raises:
            ValueError: Decision と conflict metadata の組み合わせが不正な場合。
        """
        if self.decision is OrderingDecisionKind.ACCEPT and self.conflict is not None:
            message = "accepted ordering decision must not contain conflict metadata"
            raise ValueError(message)
        if self.decision is not OrderingDecisionKind.ACCEPT and self.conflict is None:
            message = "non-accepted ordering decision requires conflict metadata"
            raise ValueError(message)
        return self
