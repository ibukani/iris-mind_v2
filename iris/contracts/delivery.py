"""配送 outbox 境界で共有する型付き契約。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.actions import ActionResult, AppAction
    from iris.core.ids import (
        AccountId,
        ActorId,
        DeliveryId,
        ExternalRef,
        LeaseId,
        SessionId,
        SpaceId,
    )


class DeliveryStatus(StrEnum):
    """配送 outbox item の明示的な状態。"""

    PENDING = "pending"
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_PERMANENT = "failed_permanent"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


TERMINAL_DELIVERY_STATUSES = frozenset(
    {
        DeliveryStatus.SUCCEEDED,
        DeliveryStatus.FAILED_PERMANENT,
        DeliveryStatus.CANCELLED,
        DeliveryStatus.BLOCKED,
    }
)


@dataclass(frozen=True)
class DeliveryRouteHint:
    """Ingress 境界で保存する外部 provider routing hint。"""

    provider: str
    provider_subject: ExternalRef | None
    provider_space_ref: ExternalRef | None
    display_name: str | None = None


@dataclass(frozen=True)
class DeliveryTarget:
    """外部 client が配送先を復元するための provider-neutral target。"""

    provider: str
    provider_subject: ExternalRef | None
    provider_space_ref: ExternalRef | None
    session_id: SessionId
    actor_id: ActorId | None = None
    account_id: AccountId | None = None
    space_id: SpaceId | None = None


@dataclass(frozen=True)
class DeliveryEnvelope:
    """DeliveryOutbox に保存・lease される配送 item。"""

    delivery_id: DeliveryId
    action: AppAction
    target: DeliveryTarget
    status: DeliveryStatus
    created_at: datetime
    updated_at: datetime
    not_before: datetime | None
    attempts: int
    max_attempts: int
    idempotency_key: str
    lease_id: LeaseId | None = None
    lease_expires_at: datetime | None = None
    blocked_reason: str | None = None
    last_error_reason: str | None = None


@dataclass(frozen=True)
class DeliveryLease:
    """外部 client へ渡す配送 lease。"""

    delivery_id: DeliveryId
    lease_id: LeaseId
    leased_at: datetime
    lease_expires_at: datetime


@dataclass(frozen=True)
class DeliveryReport:
    """外部 client が ActionResult を報告するための契約。"""

    delivery_id: DeliveryId
    lease_id: LeaseId | None
    result: ActionResult
    reported_at: datetime
