"""gRPC servicer adapter for IrisRuntimeService."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, override

import grpc

from iris.adapters.grpc.mappers import (
    GrpcMappingError,
    GrpcRuntimeMapper,
    runtime_response_to_proto,
)
from iris.generated.iris.runtime.v1 import runtime_pb2, runtime_pb2_grpc

if TYPE_CHECKING:
    from iris.runtime.service import IrisRuntimeService

_LOGGER = logging.getLogger(__name__)


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
        try:
            envelope = await self._mapper.observation_envelope_from_proto(request)
            response = await self._runtime_service.handle_observation(envelope)
            return runtime_response_to_proto(response)
        except GrpcMappingError as exc:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        except Exception:
            _LOGGER.exception("runtime service failed")
            await context.abort(grpc.StatusCode.INTERNAL, "runtime service failed")
