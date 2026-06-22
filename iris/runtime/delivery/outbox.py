"""Delivery outbox runtime port."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.actions import ActionResult
    from iris.contracts.delivery import DeliveryEnvelope
    from iris.core.ids import DeliveryId, LeaseId


class DeliveryOutboxError(RuntimeError):
    """Delivery outbox state transition failed."""


class DeliveryOutbox(Protocol):
    """Durable-compatible port for pull-based external delivery."""

    async def enqueue(self, envelope: DeliveryEnvelope) -> DeliveryEnvelope:
        """Store a pending delivery item idempotently."""
        ...

    async def lease_due(
        self,
        *,
        provider: str,
        now: datetime,
        max_items: int,
        lease_seconds: float,
    ) -> tuple[DeliveryEnvelope, ...]:
        """Lease due items for one provider."""
        ...

    async def complete(
        self,
        *,
        delivery_id: DeliveryId,
        lease_id: LeaseId | None,
        result: ActionResult,
        completed_at: datetime,
    ) -> DeliveryEnvelope:
        """Complete a leased item from an ActionResult."""
        ...

    async def release(
        self,
        *,
        delivery_id: DeliveryId,
        lease_id: LeaseId | None,
        retry_after: datetime,
        result: ActionResult,
        released_at: datetime,
    ) -> DeliveryEnvelope:
        """Release a leased item for retry or permanent failure."""
        ...

    async def mark_blocked(
        self,
        *,
        delivery_id: DeliveryId,
        reason: str,
        blocked_at: datetime,
    ) -> DeliveryEnvelope:
        """Mark an item blocked by delivery safety."""
        ...
