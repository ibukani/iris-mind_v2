"""Runtime implementation of the app action broker boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, override

from iris.adapters.app_gateway.ports import AppActionBroker
from iris.contracts.actions import ActionStatus

if TYPE_CHECKING:
    from iris.contracts.delivery import DeliveryEnvelope, DeliveryReport
    from iris.runtime.delivery.outbox import DeliveryOutbox

_TERMINAL_REPORT_STATUSES: frozenset[ActionStatus] = frozenset(
    {
        ActionStatus.SUCCEEDED,
        ActionStatus.CANCELLED,
        ActionStatus.BLOCKED,
    },
)


@dataclass(frozen=True)
class RuntimeAppActionBroker(AppActionBroker):
    """Pull-based broker backed by a DeliveryOutbox."""

    outbox: DeliveryOutbox
    lease_seconds: float = 30.0
    retry_backoff_seconds: float = 30.0

    @override
    async def poll_actions(
        self,
        *,
        provider: str,
        now: datetime,
        max_items: int,
    ) -> tuple[DeliveryEnvelope, ...]:
        """Lease due app actions for one provider.

        Returns:
            Leased delivery envelopes for the provider.
        """
        return await self.outbox.lease_due(
            provider=provider,
            now=now,
            max_items=max_items,
            lease_seconds=self.lease_seconds,
        )

    @override
    async def report_action_result(self, report: DeliveryReport) -> DeliveryEnvelope:
        """Apply an ActionResult to the leased delivery item.

        SUCCEEDED, CANCELLED, and BLOCKED are terminal completions.
        Only FAILED is released for retry or permanent failure.

        Returns:
            Updated delivery envelope after completion or release.
        """
        if report.result.status in _TERMINAL_REPORT_STATUSES:
            return await self.outbox.complete(
                delivery_id=report.delivery_id,
                lease_id=report.lease_id,
                result=report.result,
                completed_at=report.reported_at,
            )
        retry_after = report.reported_at + timedelta(seconds=self.retry_backoff_seconds)
        return await self.outbox.release(
            delivery_id=report.delivery_id,
            lease_id=report.lease_id,
            retry_after=retry_after,
            reason=report.result.error_reason or report.result.status.value,
            released_at=report.reported_at,
        )
