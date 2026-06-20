"""Delivery outbox と broker の runtime wiring。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.runtime.config.delivery import RuntimeDeliveryConfig, quiet_time
from iris.runtime.delivery.broker import RuntimeAppActionBroker
from iris.safety.delivery_gate import BasicDeliverySafetyGate, QuietHoursPolicy

if TYPE_CHECKING:
    from iris.runtime.delivery.outbox import DeliveryOutbox


def wire_app_action_broker(
    outbox: DeliveryOutbox,
    config: RuntimeDeliveryConfig,
) -> RuntimeAppActionBroker:
    """DeliveryOutbox backed AppActionBroker を組み立てる。

    Returns:
        構成済みの RuntimeAppActionBroker。
    """
    return RuntimeAppActionBroker(
        outbox=outbox,
        lease_seconds=config.lease_seconds,
        retry_backoff_seconds=config.retry_backoff_seconds,
    )


def wire_delivery_safety_gate(config: RuntimeDeliveryConfig) -> BasicDeliverySafetyGate:
    """Runtime config から delivery safety gate を組み立てる。

    Returns:
        構成済みの BasicDeliverySafetyGate。
    """
    return BasicDeliverySafetyGate(
        quiet_hours=QuietHoursPolicy(
            enabled=config.quiet_hours.enabled,
            start=quiet_time(config.quiet_hours.start, "delivery.quiet_hours.start"),
            end=quiet_time(config.quiet_hours.end, "delivery.quiet_hours.end"),
            timezone=config.quiet_hours.timezone,
        ),
    )
