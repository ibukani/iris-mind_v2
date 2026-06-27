"""Delivery outbox runtime port."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from iris.contracts.delivery import DeliveryEnvelope, DeliveryOutboxError

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.actions import ActionResult
    from iris.core.ids import DeliveryId, LeaseId

__all__ = ["DeliveryOutbox", "DeliveryOutboxError"]


class DeliveryOutbox(Protocol):
    """Durable-compatible port for pull-based external delivery."""

    async def enqueue(self, envelope: DeliveryEnvelope) -> DeliveryEnvelope:
        """Store pending delivery item idempotently."""
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

    async def get(self, delivery_id: DeliveryId) -> DeliveryEnvelope:
        """Return delivery envelope without mutating state."""
        ...

    async def complete(
        self,
        *,
        delivery_id: DeliveryId,
        lease_id: LeaseId | None,
        result: ActionResult,
        completed_at: datetime,
    ) -> DeliveryEnvelope:
        """Complete leased item with ActionResult."""
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
        """Release leased item for retry or permanent failure."""
        ...
