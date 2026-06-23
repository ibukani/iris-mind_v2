"""Runtime gRPC delivery API tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import grpc
import pytest

from iris.adapters.app_gateway.ports import AppActionBrokerError
from iris.adapters.grpc.mappers import delivery_report_from_proto
from iris.adapters.grpc.server import IrisRuntimeGrpcServicer
from iris.contracts.actions import ActionResult, ActionStatus
from iris.contracts.delivery import DeliveryReport, DeliveryStatus
from iris.core.ids import ExternalRef
from iris.generated.iris.runtime.v1 import runtime_pb2, runtime_pb2_grpc
from iris.runtime.config import default_runtime_config
from iris.runtime.delivery.broker import RuntimeAppActionBroker
from iris.runtime.delivery.in_memory import InMemoryDeliveryOutbox
from iris.runtime.server import build_runtime_components
from tests.helpers.grpc_test import RecordingRuntimeService
from tests.runtime.delivery.test_in_memory_delivery_outbox import envelope

if TYPE_CHECKING:
    from types import TracebackType

    from iris.adapters.app_gateway.ports import AppActionBroker

pytestmark = pytest.mark.anyio


async def test_poll_app_actions_leases_provider_scoped_actions() -> None:
    """Broker-backed API path leases only matching provider actions."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope(provider="discord"))
    await outbox.enqueue(envelope("delivery-2", provider="slack", idempotency_key="idem-2"))
    actions = await broker.poll_actions(provider="discord", now=now, max_items=10)
    assert len(actions) == 1
    assert actions[0].target.provider == "discord"


async def test_report_action_result_success_completes_delivery() -> None:
    """ReportActionResult success completes delivery."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]
    completed = await broker.report_action_result(
        DeliveryReport(
            delivery_id=leased.delivery_id,
            lease_id=leased.lease_id,
            result=ActionResult(
                action_id=leased.action.action_id,
                correlation_id=leased.action.correlation_id,
                status=ActionStatus.SUCCEEDED,
                delivered_at=now,
                external_message_id=ExternalRef("msg-1"),
                error_reason=None,
            ),
            reported_at=now,
        )
    )
    assert completed.status is DeliveryStatus.SUCCEEDED


async def test_report_action_result_failure_releases_or_permanently_fails() -> None:
    """Failure reports release retryable item or permanent after max attempts."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope(max_attempts=1))
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]
    failed = await broker.report_action_result(
        DeliveryReport(
            delivery_id=leased.delivery_id,
            lease_id=leased.lease_id,
            result=ActionResult(
                action_id=leased.action.action_id,
                correlation_id=leased.action.correlation_id,
                status=ActionStatus.FAILED,
                delivered_at=None,
                external_message_id=None,
                error_reason="network",
            ),
            reported_at=now,
        )
    )
    assert failed.status is DeliveryStatus.FAILED_PERMANENT


def test_report_action_result_proto_mapping_is_idempotent_safe_contract() -> None:
    """Report DTO keeps delivery and lease identifiers for idempotent completion."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    report = delivery_report_from_proto(
        runtime_pb2.ReportActionResultRequest(
            delivery_id="delivery-1",
            lease_id="lease-1",
            action_id="action-1",
            correlation_id="corr-1",
            status="succeeded",
        ),
        now,
    )
    assert report.delivery_id == "delivery-1"
    assert report.lease_id == "lease-1"


async def test_report_action_result_failed_is_idempotent() -> None:
    """Repeated identical FAILED report is safe."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope(max_attempts=3))
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]
    report = DeliveryReport(
        delivery_id=leased.delivery_id,
        lease_id=leased.lease_id,
        result=ActionResult(
            action_id=leased.action.action_id,
            correlation_id=leased.action.correlation_id,
            status=ActionStatus.FAILED,
            delivered_at=None,
            external_message_id=None,
            error_reason="network",
        ),
        reported_at=now,
    )
    first = await broker.report_action_result(report)
    second = await broker.report_action_result(report)
    assert second.delivery_id == first.delivery_id


async def test_report_action_result_cancelled_is_terminal() -> None:
    """CANCELLED report becomes terminal DeliveryStatus.CANCELLED."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]
    cancelled = await broker.report_action_result(
        DeliveryReport(
            delivery_id=leased.delivery_id,
            lease_id=leased.lease_id,
            result=ActionResult(
                action_id=leased.action.action_id,
                correlation_id=leased.action.correlation_id,
                status=ActionStatus.CANCELLED,
                delivered_at=None,
                external_message_id=None,
                error_reason=None,
            ),
            reported_at=now,
        )
    )
    assert cancelled.status is DeliveryStatus.CANCELLED
    repeated = await broker.report_action_result(
        DeliveryReport(
            delivery_id=leased.delivery_id,
            lease_id=leased.lease_id,
            result=ActionResult(
                action_id=leased.action.action_id,
                correlation_id=leased.action.correlation_id,
                status=ActionStatus.CANCELLED,
                delivered_at=None,
                external_message_id=None,
                error_reason=None,
            ),
            reported_at=now,
        )
    )
    assert repeated.status is DeliveryStatus.CANCELLED


async def test_report_action_result_blocked_is_terminal() -> None:
    """BLOCKED report becomes terminal DeliveryStatus.BLOCKED."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]
    blocked = await broker.report_action_result(
        DeliveryReport(
            delivery_id=leased.delivery_id,
            lease_id=leased.lease_id,
            result=ActionResult(
                action_id=leased.action.action_id,
                correlation_id=leased.action.correlation_id,
                status=ActionStatus.BLOCKED,
                delivered_at=None,
                external_message_id=None,
                error_reason="policy",
            ),
            reported_at=now,
        )
    )
    assert blocked.status is DeliveryStatus.BLOCKED
    repeated = await broker.report_action_result(
        DeliveryReport(
            delivery_id=leased.delivery_id,
            lease_id=leased.lease_id,
            result=ActionResult(
                action_id=leased.action.action_id,
                correlation_id=leased.action.correlation_id,
                status=ActionStatus.BLOCKED,
                delivered_at=None,
                external_message_id=None,
                error_reason="policy",
            ),
            reported_at=now,
        )
    )
    assert repeated.status is DeliveryStatus.BLOCKED


async def test_report_action_result_external_message_id_conflict_raises() -> None:
    """ReportActionResult conflicts when external message id changes."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]

    await broker.report_action_result(
        DeliveryReport(
            delivery_id=leased.delivery_id,
            lease_id=leased.lease_id,
            result=ActionResult(
                action_id=leased.action.action_id,
                correlation_id=leased.action.correlation_id,
                status=ActionStatus.SUCCEEDED,
                delivered_at=now,
                external_message_id=ExternalRef("msg-1"),
                error_reason=None,
            ),
            reported_at=now,
        )
    )

    with pytest.raises(AppActionBrokerError, match="delivery_report_conflict"):
        await broker.report_action_result(
            DeliveryReport(
                delivery_id=leased.delivery_id,
                lease_id=leased.lease_id,
                result=ActionResult(
                    action_id=leased.action.action_id,
                    correlation_id=leased.action.correlation_id,
                    status=ActionStatus.SUCCEEDED,
                    delivered_at=now,
                    external_message_id=ExternalRef("msg-2"),
                    error_reason=None,
                ),
                reported_at=now,
            )
        )


async def test_report_action_result_unknown_delivery_id_returns_not_found() -> None:
    """Unknown delivery report maps to NOT_FOUND."""
    broker = RuntimeAppActionBroker(outbox=InMemoryDeliveryOutbox())

    async with _DeliveryGrpcHarness(broker) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.ReportActionResult(_report_request(delivery_id="missing"))

    assert exc_info.value.code() is grpc.StatusCode.NOT_FOUND


async def test_report_action_result_lease_mismatch_returns_failed_precondition() -> None:
    """Mismatched lease maps to FAILED_PRECONDITION."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]

    async with _DeliveryGrpcHarness(broker) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.ReportActionResult(
                _report_request(
                    delivery_id=str(leased.delivery_id),
                    lease_id="wrong-lease",
                    action_id=str(leased.action.action_id),
                    correlation_id=str(leased.action.correlation_id),
                ),
            )

    assert exc_info.value.code() is grpc.StatusCode.FAILED_PRECONDITION


async def test_report_action_result_conflict_returns_already_exists() -> None:
    """Conflicting repeated report maps to ALREADY_EXISTS."""
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await outbox.enqueue(envelope())
    leased = (await broker.poll_actions(provider="discord", now=now, max_items=1))[0]

    first = _report_request(
        delivery_id=str(leased.delivery_id),
        lease_id=str(leased.lease_id),
        action_id=str(leased.action.action_id),
        correlation_id=str(leased.action.correlation_id),
        external_message_id="msg-1",
    )
    conflicting = _report_request(
        delivery_id=str(leased.delivery_id),
        lease_id=str(leased.lease_id),
        action_id=str(leased.action.action_id),
        correlation_id=str(leased.action.correlation_id),
        external_message_id="msg-2",
    )

    async with _DeliveryGrpcHarness(broker) as stub:
        await stub.ReportActionResult(first)
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.ReportActionResult(conflicting)

    assert exc_info.value.code() is grpc.StatusCode.ALREADY_EXISTS


async def test_report_action_result_invalid_proto_returns_invalid_argument() -> None:
    """Invalid report proto maps before broker transition."""
    broker = RuntimeAppActionBroker(outbox=InMemoryDeliveryOutbox())

    async with _DeliveryGrpcHarness(broker) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.ReportActionResult(_report_request(status="bad"))

    assert exc_info.value.code() is grpc.StatusCode.INVALID_ARGUMENT


async def test_delivery_disabled_wiring_rejects_poll_and_report() -> None:
    """delivery.enabled=false disables gRPC delivery APIs through runtime wiring."""
    config = default_runtime_config()
    config = replace(config, delivery=replace(config.delivery, enabled=False))
    components = build_runtime_components(config)

    async with _DeliveryGrpcHarness(components.app_action_broker) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as poll_exc:
            await stub.PollAppActions(
                runtime_pb2.PollAppActionsRequest(provider="discord", max_items=1),
            )
        with pytest.raises(grpc.aio.AioRpcError) as report_exc:
            await stub.ReportActionResult(_report_request())

    assert poll_exc.value.code() is grpc.StatusCode.FAILED_PRECONDITION
    assert report_exc.value.code() is grpc.StatusCode.FAILED_PRECONDITION


async def test_get_runtime_info_includes_delivery_features_when_broker_present() -> None:
    """GetRuntimeInfo advertises delivery features when broker is wired."""
    broker = RuntimeAppActionBroker(outbox=InMemoryDeliveryOutbox())

    async with _DeliveryGrpcHarness(broker) as stub:
        response = await stub.GetRuntimeInfo(runtime_pb2.GetRuntimeInfoRequest())

    assert "poll_app_actions" in response.supported_features
    assert "report_action_result" in response.supported_features


def _report_request(
    *,
    delivery_id: str = "delivery-1",
    lease_id: str = "lease-1",
    action_id: str = "action-1",
    correlation_id: str = "corr-1",
    status: str = "succeeded",
    external_message_id: str = "msg-1",
) -> runtime_pb2.ReportActionResultRequest:
    """Build ReportActionResultRequest for gRPC tests.

    Returns:
        ReportActionResultRequest with required delivery fields.
    """
    return runtime_pb2.ReportActionResultRequest(
        delivery_id=delivery_id,
        lease_id=lease_id,
        action_id=action_id,
        correlation_id=correlation_id,
        status=status,
        external_message_id=external_message_id,
    )


class _DeliveryGrpcHarness:
    """In-process gRPC server for delivery API tests."""

    def __init__(self, app_action_broker: AppActionBroker | None) -> None:
        """Create harness with optional app action broker."""
        self._app_action_broker = app_action_broker
        self._server: grpc.aio.Server | None = None
        self._channel: grpc.aio.Channel | None = None

    async def __aenter__(self) -> runtime_pb2_grpc.IrisRuntimeServiceAsyncStub:
        """Start server and return connected stub.

        Returns:
            Connected async runtime service stub.
        """
        server = grpc.aio.server()
        runtime_pb2_grpc.add_IrisRuntimeServiceServicer_to_server(
            IrisRuntimeGrpcServicer(
                RecordingRuntimeService("unused"),
                app_action_broker=self._app_action_broker,
            ),
            server,
        )
        port = server.add_insecure_port("127.0.0.1:0")
        await server.start()
        channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
        self._server = server
        self._channel = channel
        return runtime_pb2_grpc.IrisRuntimeServiceStub(channel)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close channel and stop server."""
        _ = exc_type, exc, traceback
        if self._channel is not None:
            await self._channel.close()
        if self._server is not None:
            await self._server.stop(0)
