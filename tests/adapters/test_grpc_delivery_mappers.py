"""gRPC delivery mapper tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.adapters.grpc.mappers import (
    GrpcMappingError,
    delivery_envelope_to_proto,
    delivery_report_from_proto,
)
from iris.contracts.actions import ActionStatus
from iris.generated.iris.runtime.v1 import runtime_pb2
from tests.runtime.delivery.test_in_memory_delivery_outbox import envelope


def test_poll_app_actions_maps_delivery_envelope_to_proto() -> None:
    """DeliveryEnvelope maps to AppActionEnvelope proto."""
    delivery = envelope()
    proto = delivery_envelope_to_proto(delivery)
    assert proto.delivery_id == "delivery-1"
    assert proto.provider == "discord"
    assert proto.send_message.text == "hello"


def test_report_action_result_success_maps_to_delivery_report() -> None:
    """ReportActionResultRequest maps status and IDs."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    report = delivery_report_from_proto(
        runtime_pb2.ReportActionResultRequest(
            delivery_id="delivery-1",
            lease_id="lease-1",
            action_id="action-1",
            correlation_id="corr-1",
            status="succeeded",
            external_message_id="msg-1",
        ),
        now,
    )
    assert report.result.status is ActionStatus.SUCCEEDED
    assert report.result.delivered_at == now


def test_report_action_result_invalid_status_rejected() -> None:
    """Invalid report status raises mapping error."""
    with pytest.raises(GrpcMappingError, match="invalid action result status"):
        delivery_report_from_proto(
            runtime_pb2.ReportActionResultRequest(
                delivery_id="delivery-1",
                action_id="action-1",
                correlation_id="corr-1",
                status="bad",
            ),
            datetime(2026, 1, 1, tzinfo=UTC),
        )
