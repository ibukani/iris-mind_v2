"""gRPC servicer adapter for IrisRuntimeService."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, override

import grpc
from loguru import logger

from iris.adapters.grpc.mappers import (
    GrpcMappingError,
    GrpcRuntimeMapper,
    runtime_response_to_proto,
)
from iris.generated.iris.runtime.v1 import runtime_pb2, runtime_pb2_grpc

if TYPE_CHECKING:
    from iris.runtime.service import IrisRuntimeService


class IrisRuntimeGrpcServicer(runtime_pb2_grpc.IrisRuntimeServiceServicer):
    """gRPC adapter that delegates SubmitObservation to IrisRuntimeService.

    The servicer holds no policy; it only routes proto DTOs through a mapper
    and forwards the resulting envelope to the runtime service.
    """

    def __init__(
        self,
        runtime_service: IrisRuntimeService,
        *,
        mapper: GrpcRuntimeMapper | None = None,
    ) -> None:
        """Create servicer with an explicit runtime service and optional mapper."""
        self._runtime_service = runtime_service
        self._mapper = mapper or GrpcRuntimeMapper()

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
        response = runtime_pb2.GetRuntimeInfoResponse(
            runtime_name="iris-mind",
            runtime_version="0.1.0",
            api_version="iris.runtime.v1",
            supported_features=[
                "submit_observation",
                "persistent_account",
                "ephemeral_space",
            ],
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
        """
        logger.info("SubmitObservation: received")
        start_time = time.monotonic()
        try:
            envelope = await self._mapper.observation_envelope_from_proto(request)
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
        except GrpcMappingError as exc:
            logger.warning("SubmitObservation: invalid_argument - {}", exc)
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        except Exception as exc:  # noqa: BLE001 -- global fallback for the runtime ingress boundary
            logger.exception("SubmitObservation: internal_error - {}", exc)
            await context.abort(grpc.StatusCode.INTERNAL, "runtime service failed")
