"""delivery contractとgRPC DTO間のmapper。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.grpc.mappers.common import raise_mapping_error
from iris.adapters.grpc.mappers.outputs import presentation_hints_to_proto
from iris.contracts.actions import ActionResult, ActionStatus, SendMessageAction
from iris.contracts.delivery import DeliveryReport
from iris.core.ids import ActionId, CorrelationId, DeliveryId, ExternalRef, LeaseId
from iris.generated.iris.runtime.v1 import runtime_pb2

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.delivery import DeliveryEnvelope


def delivery_envelope_to_proto(envelope: DeliveryEnvelope) -> runtime_pb2.AppActionEnvelope:
    """lease済みDeliveryEnvelopeをpolling DTOへ変換する。

    Returns:
        protobuf AppActionEnvelope。
    """
    action = envelope.action
    if not isinstance(action, SendMessageAction):
        raise_mapping_error("unsupported delivery action")
    return runtime_pb2.AppActionEnvelope(
        delivery_id=str(envelope.delivery_id),
        lease_id=str(envelope.lease_id or ""),
        action_id=str(action.action_id),
        correlation_id=str(action.correlation_id),
        session_id=str(action.session_id),
        provider=envelope.target.provider,
        provider_subject=str(envelope.target.provider_subject or ""),
        provider_space_ref=str(envelope.target.provider_space_ref or ""),
        attempts=envelope.attempts,
        send_message=runtime_pb2.SendMessageAction(
            text=action.text,
            presentation_hints=presentation_hints_to_proto(action.presentation_hints),
        ),
    )


def delivery_envelopes_to_poll_response(
    envelopes: tuple[DeliveryEnvelope, ...],
) -> runtime_pb2.PollAppActionsResponse:
    """lease済みenvelope群をPollAppActionsResponseへ変換する。

    Returns:
        protobuf PollAppActionsResponse。
    """
    return runtime_pb2.PollAppActionsResponse(
        actions=[delivery_envelope_to_proto(envelope) for envelope in envelopes],
    )


def delivery_id_from_report_proto(
    request: runtime_pb2.ReportActionResultRequest,
) -> DeliveryId:
    """ReportActionResultRequestからDeliveryIdを検証・抽出する。

    Returns:
        検証済みDeliveryId。
    """
    if not request.delivery_id:
        raise_mapping_error("delivery_id required")
    return DeliveryId(request.delivery_id)


def delivery_report_from_proto(
    request: runtime_pb2.ReportActionResultRequest,
    reported_at: datetime,
) -> DeliveryReport:
    """ReportActionResultRequestをDeliveryReportへ変換する。

    Returns:
        typed DeliveryReport。
    """
    delivery_id = delivery_id_from_report_proto(request)
    status = _action_status_from_report_status(request.status)
    if not request.action_id:
        raise_mapping_error("action_id required")
    if not request.correlation_id:
        raise_mapping_error("correlation_id required")
    return DeliveryReport(
        delivery_id=delivery_id,
        lease_id=LeaseId(request.lease_id) if request.lease_id else None,
        result=ActionResult(
            action_id=ActionId(request.action_id),
            correlation_id=CorrelationId(request.correlation_id),
            status=status,
            delivered_at=reported_at if status is ActionStatus.SUCCEEDED else None,
            external_message_id=(
                ExternalRef(request.external_message_id) if request.external_message_id else None
            ),
            error_reason=request.error_reason or None,
        ),
        reported_at=reported_at,
    )


def _action_status_from_report_status(status: str) -> ActionStatus:
    try:
        return ActionStatus(status)
    except ValueError as exc:
        raise_mapping_error(f"invalid action result status: {status}", cause=exc)
