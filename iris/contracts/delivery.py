"""配送 outbox 境界で共有する型付き契約。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

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


class DeliveryOutboxError(RuntimeError):
    """Delivery outbox state transition failed."""


class DeliveryRouteHint(BaseModel):
    """Ingress 境界で保存する外部 provider routing hint。"""

    model_config = ConfigDict(frozen=True)

    provider: str
    provider_subject: ExternalRef | None
    provider_space_ref: ExternalRef | None
    display_name: str | None = None


class SchedulerTarget(BaseModel):
    """Scheduler が IdleTickObservation を作る候補 target。"""

    model_config = ConfigDict(frozen=True)

    actor_id: ActorId | None
    account_id: AccountId | None
    space_id: SpaceId | None
    session_id: SessionId
    route: DeliveryRouteHint
    display_name: str | None
    last_observed_at: datetime
    last_scheduler_attempt_at: datetime | None = None
    stale_after: datetime | None = None


class DeliveryTarget(BaseModel):
    """外部 client が配送先を復元するための provider-neutral target。"""

    model_config = ConfigDict(frozen=True)

    provider: str
    provider_subject: ExternalRef | None
    provider_space_ref: ExternalRef | None
    session_id: SessionId
    actor_id: ActorId | None = None
    account_id: AccountId | None = None
    space_id: SpaceId | None = None


class DeliveryEnvelope(BaseModel):
    """DeliveryOutbox に保存・lease される配送 item。"""

    model_config = ConfigDict(frozen=True)

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


class DeliveryLease(BaseModel):
    """外部 client へ渡す配送 lease。"""

    model_config = ConfigDict(frozen=True)

    delivery_id: DeliveryId
    lease_id: LeaseId
    leased_at: datetime
    lease_expires_at: datetime


class DeliveryReport(BaseModel):
    """外部 client が ActionResult を報告するための契約。"""

    model_config = ConfigDict(frozen=True)

    delivery_id: DeliveryId
    lease_id: LeaseId | None
    result: ActionResult
    reported_at: datetime
