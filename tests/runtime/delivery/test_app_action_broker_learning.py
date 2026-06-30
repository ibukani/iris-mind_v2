"""App action broker learning integration tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from iris.adapters.app_gateway.ports import AppActionBrokerError
from iris.contracts.actions import ActionResult, ActionStatus
from iris.contracts.delivery import DeliveryEnvelope, DeliveryReport
from iris.core.ids import ExternalRef
from iris.runtime.delivery.broker import RuntimeAppActionBroker
from iris.runtime.delivery.in_memory import InMemoryDeliveryOutbox
from iris.runtime.learning.dispatch import InMemoryLearningDispatchStore
from iris.runtime.learning.hooks import LearningHookRunner
from tests.runtime.delivery.test_in_memory_delivery_outbox import envelope

if TYPE_CHECKING:
    from iris.contracts.learning import LearningEvent

pytestmark = pytest.mark.anyio


class _EventHook:
    def __init__(self, *, fail: bool = False) -> None:
        self.events: list[LearningEvent] = []
        self._fail = fail

    async def after_action_result(self, event: LearningEvent) -> None:
        self.events.append(event)
        if self._fail:
            message = "hook failure"
            raise RuntimeError(message)


async def _leased_broker(hook: _EventHook) -> tuple[RuntimeAppActionBroker, DeliveryEnvelope]:
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(
        outbox=outbox,
        learning_hook_runner=LearningHookRunner((hook,)),
        learning_dispatch_store=InMemoryLearningDispatchStore(),
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]
    return broker, leased


def _report(leased: DeliveryEnvelope, status: ActionStatus) -> DeliveryReport:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return DeliveryReport(
        delivery_id=leased.delivery_id,
        lease_id=leased.lease_id,
        result=ActionResult(
            action_id=leased.action.action_id,
            correlation_id=leased.action.correlation_id,
            status=status,
            delivered_at=now if status is ActionStatus.SUCCEEDED else None,
            external_message_id=(
                ExternalRef("message-1") if status is ActionStatus.SUCCEEDED else None
            ),
            error_reason="failed" if status is ActionStatus.FAILED else None,
        ),
        reported_at=now,
    )


@pytest.mark.parametrize(
    "status",
    [
        pytest.param(ActionStatus.SUCCEEDED),
        pytest.param(ActionStatus.BLOCKED),
        pytest.param(ActionStatus.FAILED),
    ],
)
async def test_accepted_report_emits_learning_event(status: ActionStatus) -> None:
    """受理された success/blocked/failed 結果から学習イベントを生成する。"""
    hook = _EventHook()
    broker, leased = await _leased_broker(hook)
    updated = await broker.report_action_result(_report(leased, status))
    assert hook.events[0].delivery == updated
    assert hook.events[0].action == leased.action
    assert hook.events[0].target == leased.target


async def test_duplicate_report_does_not_emit_duplicate_learning_event() -> None:
    """同一結果報告は学習イベントを重複生成しない。"""
    hook = _EventHook()
    broker, leased = await _leased_broker(hook)
    report = _report(leased, ActionStatus.SUCCEEDED)
    await broker.report_action_result(report)
    await broker.report_action_result(report)
    assert len(hook.events) == 1


async def test_conflicting_transition_does_not_emit_learning_event() -> None:
    """拒否された競合遷移は学習イベントを生成しない。"""
    hook = _EventHook()
    broker, leased = await _leased_broker(hook)
    await broker.report_action_result(_report(leased, ActionStatus.SUCCEEDED))
    with pytest.raises(AppActionBrokerError):
        await broker.report_action_result(_report(leased, ActionStatus.BLOCKED))
    assert len(hook.events) == 1


async def test_hook_failure_does_not_fail_report() -> None:
    """学習フック障害を配送結果報告から隔離する。"""
    hook = _EventHook(fail=True)
    broker, leased = await _leased_broker(hook)
    updated = await broker.report_action_result(_report(leased, ActionStatus.SUCCEEDED))
    assert updated.delivery_id == leased.delivery_id
