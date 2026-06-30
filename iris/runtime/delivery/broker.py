"""Runtime implementation of the app action broker boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import TYPE_CHECKING, override

from iris.adapters.app_gateway.ports import AppActionBroker, AppActionBrokerError
from iris.contracts.actions import ActionStatus
from iris.contracts.learning import LearningEvent
from iris.runtime.delivery.outbox import DeliveryOutboxError

if TYPE_CHECKING:
    from iris.contracts.delivery import DeliveryEnvelope, DeliveryReport
    from iris.core.ids import DeliveryId
    from iris.runtime.delivery.outbox import DeliveryOutbox
    from iris.runtime.learning.dispatch import LearningDispatchStore
    from iris.runtime.learning.hooks import LearningHookRunner


_TERMINAL_REPORT_STATUSES: frozenset[ActionStatus] = frozenset(
    {
        ActionStatus.SUCCEEDED,
        ActionStatus.CANCELLED,
        ActionStatus.BLOCKED,
    },
)


@dataclass(frozen=True)
class RuntimeAppActionBroker(AppActionBroker):
    """Pull-based broker backed by DeliveryOutbox."""

    outbox: DeliveryOutbox
    lease_seconds: float = 30.0
    retry_backoff_seconds: float = 30.0
    learning_hook_runner: LearningHookRunner | None = None
    learning_dispatch_store: LearningDispatchStore | None = None

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
            Leased delivery envelopes for provider.

        Raises:
            AppActionBrokerError: outbox transition fails.
        """
        try:
            return await self.outbox.lease_due(
                provider=provider,
                now=now,
                max_items=max_items,
                lease_seconds=self.lease_seconds,
            )
        except DeliveryOutboxError as exc:
            raise AppActionBrokerError(str(exc)) from exc

    @override
    async def get_delivery_provider(self, delivery_id: DeliveryId) -> str:
        """delivery_id から provider を read-only で解決する。

        outbox の状態を変更せず、認可判定用の provider 文字列のみ返す。

        Returns:
            Delivery target provider。

        Raises:
            AppActionBrokerError: outbox lookup に失敗した場合。
        """
        try:
            existing = await self.outbox.get(delivery_id)
        except DeliveryOutboxError as exc:
            raise AppActionBrokerError(str(exc)) from exc
        return existing.target.provider

    @override
    async def report_action_result(self, report: DeliveryReport) -> DeliveryEnvelope:
        """Apply ActionResult to a leased delivery item.

        SUCCEEDED, CANCELLED, BLOCKED are terminal completions.
        FAILED releases for retry or permanent failure.

        Returns:
            Updated delivery envelope after completion or release.

        Raises:
            AppActionBrokerError: outbox transition fails.
        """
        try:
            if report.result.status in _TERMINAL_REPORT_STATUSES:
                updated = await self.outbox.complete(
                    delivery_id=report.delivery_id,
                    lease_id=report.lease_id,
                    result=report.result,
                    completed_at=report.reported_at,
                )
            else:
                retry_after = report.reported_at + timedelta(
                    seconds=self.retry_backoff_seconds,
                )
                updated = await self.outbox.release(
                    delivery_id=report.delivery_id,
                    lease_id=report.lease_id,
                    retry_after=retry_after,
                    result=report.result,
                    released_at=report.reported_at,
                )
        except DeliveryOutboxError as exc:
            raise AppActionBrokerError(str(exc)) from exc
        await self._dispatch_learning(report, updated)
        return updated

    async def _dispatch_learning(
        self,
        report: DeliveryReport,
        delivery: DeliveryEnvelope,
    ) -> None:
        """受理済み配送遷移を一度だけ学習フックへ渡す。"""
        if self.learning_hook_runner is None or self.learning_dispatch_store is None:
            return
        key = _learning_dispatch_key(report)
        if not await self.learning_dispatch_store.mark_if_absent(key):
            return
        await self.learning_hook_runner.run(
            LearningEvent(
                result=report.result,
                delivery=delivery,
                action=delivery.action,
                target=delivery.target,
                reported_at=report.reported_at,
                source_observation_id=delivery.source_observation_id,
            )
        )


def _learning_dispatch_key(report: DeliveryReport) -> str:
    """論理的な結果報告から安定 dispatch key を生成する。

    Returns:
        結果報告の SHA-256 key。
    """
    result = report.result
    material = "|".join(
        (
            str(report.delivery_id),
            str(report.lease_id or ""),
            str(result.action_id),
            str(result.correlation_id),
            result.status.value,
            str(result.external_message_id or ""),
            result.error_reason or "",
        )
    )
    return sha256(material.encode()).hexdigest()
