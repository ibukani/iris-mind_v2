"""gRPC servicer adapter for IrisRuntimeService."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, override

import grpc
from loguru import logger

from iris.adapters.app_gateway.ports import AppActionBrokerError, AppActionBrokerErrorReason
from iris.adapters.grpc.mappers import (
    GrpcMappingError,
    GrpcRuntimeMapper,
    delivery_envelopes_to_poll_response,
    delivery_id_from_report_proto,
    delivery_report_from_proto,
    map_exception_to_grpc,
    runtime_response_to_proto,
)
from iris.adapters.llm.diagnostics import LLMProviderError
from iris.core.datetime_utils import now_utc
from iris.generated.iris.runtime.v1 import runtime_pb2, runtime_pb2_grpc
from iris.runtime.auth.context import current_principal
from iris.runtime.auth.errors import RuntimePermissionDeniedError
from iris.runtime.auth.policy import (
    ObservationRequestClaims,
    RuntimeAuthorizationPolicy,
)

if TYPE_CHECKING:
    from iris.adapters.app_gateway.ports import AppActionBroker
    from iris.runtime.service import IrisRuntimeService, ObservationEnvelope


class IrisRuntimeGrpcServicer(runtime_pb2_grpc.IrisRuntimeServiceServicer):
    """gRPC adapter that delegates SubmitObservation to IrisRuntimeService.

    The servicer holds no policy; it only routes proto DTOs through a mapper
    and forwards the resulting envelope to the runtime service.
    """

    def __init__(
        self,
        runtime_service: IrisRuntimeService,
        *,
        app_action_broker: AppActionBroker | None = None,
        mapper: GrpcRuntimeMapper | None = None,
        authorization_policy: RuntimeAuthorizationPolicy | None = None,
    ) -> None:
        """Create servicer with explicit runtime service and mapper."""
        self._runtime_service = runtime_service
        self._app_action_broker = app_action_broker
        self._mapper = mapper or GrpcRuntimeMapper()
        self._authorization_policy = authorization_policy or RuntimeAuthorizationPolicy()

    @override
    async def GetRuntimeInfo(
        self,
        request: runtime_pb2.GetRuntimeInfoRequest,
        context: grpc.aio.ServicerContext[
            runtime_pb2.GetRuntimeInfoRequest,
            runtime_pb2.GetRuntimeInfoResponse,
        ],
    ) -> runtime_pb2.GetRuntimeInfoResponse:
        """Handle unary GetRuntimeInfo RPC.

        Returns:
            runtime_pb2.GetRuntimeInfoResponse: Proto runtime info response.
        """
        logger.info("GetRuntimeInfo: received")
        try:
            self._authorization_policy.require_runtime_info(current_principal())
        except RuntimePermissionDeniedError as exc:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, str(exc))
        supported_features = [
            "submit_observation",
            "persistent_account",
            "ephemeral_space",
        ]
        if self._app_action_broker is not None:
            supported_features.extend(
                [
                    "poll_app_actions",
                    "report_action_result",
                ],
            )
        response = runtime_pb2.GetRuntimeInfoResponse(
            runtime_name="iris-mind",
            runtime_version="0.1.0",
            api_version="iris.runtime.v1",
            supported_features=supported_features,
        )
        logger.info("GetRuntimeInfo: completed")
        return response

    @override
    async def SubmitObservation(
        self,
        request: runtime_pb2.SubmitObservationRequest,
        context: grpc.aio.ServicerContext[
            runtime_pb2.SubmitObservationRequest,
            runtime_pb2.SubmitObservationResponse,
        ],
    ) -> runtime_pb2.SubmitObservationResponse:
        """Handle unary SubmitObservation RPC.

        Returns:
            runtime_pb2.SubmitObservationResponse: Proto runtime response.

        Raises:
            asyncio.CancelledError: Propagated when client cancels RPC.
        """
        logger.info("SubmitObservation: received")
        start_time = time.monotonic()
        try:
            envelope = await self._authorized_observation_envelope(request)
            response = await self._runtime_service.handle_observation(envelope)
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.bind(
                correlation_id=str(envelope.correlation_id),
                observation_id=str(envelope.observation.observation_id),
                session_id=str(envelope.observation.session_id),
                kind=envelope.observation.kind.value,
                source=envelope.observation.context.source,
                has_account_ref=request.observation.context.HasField("account_ref"),
                has_space_ref=request.observation.context.HasField("space_ref"),
                latency_ms=round(latency_ms, 2),
            ).info("SubmitObservation: completed")
            return runtime_response_to_proto(response)
        except RuntimePermissionDeniedError as exc:
            logger.warning("SubmitObservation: permission_denied - {}", exc)
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, str(exc))
        except GrpcMappingError as exc:
            logger.warning("SubmitObservation: invalid_argument - {}", exc)
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        except asyncio.CancelledError:
            logger.warning("SubmitObservation: cancelled by client")
            raise
        except LLMProviderError as exc:
            status, message = map_exception_to_grpc(exc)
            log = logger.exception if status is grpc.StatusCode.INTERNAL else logger.warning
            log("SubmitObservation: {} - {}", status.name, exc)
            await context.abort(status, message)
        except (RuntimeError, ValueError, KeyError, AttributeError) as exc:
            logger.exception("SubmitObservation: ingress_runtime_error - {}", exc)
            await context.abort(grpc.StatusCode.INTERNAL, "runtime service failed")

    async def _authorized_observation_envelope(
        self,
        request: runtime_pb2.SubmitObservationRequest,
    ) -> ObservationEnvelope:
        principal = current_principal()
        self._authorization_policy.require_submit_observation(
            principal,
            _observation_claims_from_request(request),
        )
        return await self._mapper.observation_envelope_from_proto(request, principal)

    @override
    async def PollAppActions(
        self,
        request: runtime_pb2.PollAppActionsRequest,
        context: grpc.aio.ServicerContext[
            runtime_pb2.PollAppActionsRequest,
            runtime_pb2.PollAppActionsResponse,
        ],
    ) -> runtime_pb2.PollAppActionsResponse:
        """Lease due app actions for a trusted local/internal client.

        Returns:
            PollAppActionsResponse: lease 済み配送 DTO。
        """
        if self._app_action_broker is None:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "app action broker disabled")
        if not request.provider:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "provider required")
        max_items = request.max_items if request.max_items > 0 else 10
        try:
            self._authorization_policy.require_poll_app_actions(
                current_principal(),
                request.provider,
            )
            envelopes = await self._app_action_broker.poll_actions(
                provider=request.provider,
                now=now_utc(),
                max_items=max_items,
            )
        except RuntimePermissionDeniedError as exc:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, str(exc))
        except AppActionBrokerError as exc:
            await context.abort(_broker_error_status(exc.reason), str(exc.reason))
        return delivery_envelopes_to_poll_response(envelopes)

    @override
    async def ReportActionResult(
        self,
        request: runtime_pb2.ReportActionResultRequest,
        context: grpc.aio.ServicerContext[
            runtime_pb2.ReportActionResultRequest,
            runtime_pb2.ReportActionResultResponse,
        ],
    ) -> runtime_pb2.ReportActionResultResponse:
        """Apply an ActionResult report from a trusted local/internal client.

        Returns:
            ReportActionResultResponse: 空応答。
        """
        if self._app_action_broker is None:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "app action broker disabled")
        try:
            principal = current_principal()
            self._authorization_policy.require_delivery_report_scope(principal)
            delivery_id = delivery_id_from_report_proto(request)
        except RuntimePermissionDeniedError as exc:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, str(exc))
        except GrpcMappingError as exc:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))

        try:
            delivery_provider = await self._app_action_broker.get_delivery_provider(delivery_id)
            self._authorization_policy.require_delivery_report_provider(
                principal,
                delivery_provider,
            )
            report = delivery_report_from_proto(request, now_utc())
            await self._app_action_broker.report_action_result(report)
        except RuntimePermissionDeniedError as exc:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, str(exc))
        except GrpcMappingError as exc:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        except AppActionBrokerError as exc:
            await context.abort(_broker_error_status(exc.reason), str(exc.reason))
        return runtime_pb2.ReportActionResultResponse()


def _observation_claims_from_request(
    request: runtime_pb2.SubmitObservationRequest,
) -> ObservationRequestClaims:
    if not request.HasField("observation") or not request.observation.HasField("context"):
        return ObservationRequestClaims()
    context = request.observation.context
    account_provider = context.account_ref.provider if context.HasField("account_ref") else None
    space_provider = context.space_ref.provider if context.HasField("space_ref") else None
    return ObservationRequestClaims(
        account_ref_provider=account_provider or None,
        space_ref_provider=space_provider or None,
        has_actor=context.HasField("actor"),
        has_account_id=bool(context.account_id),
        has_space_id=bool(context.space_id),
    )


def _broker_error_status(reason: AppActionBrokerErrorReason | str) -> grpc.StatusCode:
    """Map stable AppActionBrokerError reason to gRPC status.

    Returns:
        grpc.StatusCode for the stable broker error reason.
    """
    if isinstance(reason, AppActionBrokerErrorReason):
        return _BROKER_ERROR_STATUS.get(reason, grpc.StatusCode.FAILED_PRECONDITION)
    return grpc.StatusCode.FAILED_PRECONDITION


_BROKER_ERROR_STATUS: dict[AppActionBrokerErrorReason, grpc.StatusCode] = {
    AppActionBrokerErrorReason.DELIVERY_NOT_FOUND: grpc.StatusCode.NOT_FOUND,
    AppActionBrokerErrorReason.LEASE_MISMATCH: grpc.StatusCode.FAILED_PRECONDITION,
    AppActionBrokerErrorReason.DELIVERY_NOT_LEASED: grpc.StatusCode.FAILED_PRECONDITION,
    AppActionBrokerErrorReason.DELIVERY_ALREADY_TERMINAL: grpc.StatusCode.FAILED_PRECONDITION,
    AppActionBrokerErrorReason.DELIVERY_REPORT_CONFLICT: grpc.StatusCode.ALREADY_EXISTS,
    AppActionBrokerErrorReason.OUTBOX_DEPTH_EXCEEDED: grpc.StatusCode.RESOURCE_EXHAUSTED,
}
