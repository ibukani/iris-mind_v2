"""Explicit gRPC runtime server wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING

import grpc

from iris.adapters.grpc.mappers import GrpcRuntimeMapper
from iris.adapters.grpc.server import IrisRuntimeGrpcServicer
from iris.generated.iris.runtime.v1 import runtime_pb2_grpc

if TYPE_CHECKING:
    from iris.adapters.app_gateway.ports import IdentityResolver
    from iris.runtime.service import IrisRuntimeService


def add_iris_runtime_servicer(
    server: grpc.aio.Server,
    runtime_service: IrisRuntimeService,
    *,
    identity_resolver: IdentityResolver | None = None,
) -> None:
    """Register IrisRuntimeGrpcServicer on a gRPC aio server.

    Args:
        server: gRPC aio server to register the servicer on.
        runtime_service: Runtime service that handles mapped observations.
        identity_resolver: Optional resolver used to map ExternalAccountRef into
            typed Identity. If omitted, the mapper rejects ExternalAccountRef
            inputs.
    """
    mapper = GrpcRuntimeMapper(identity_resolver=identity_resolver)
    runtime_pb2_grpc.add_IrisRuntimeServiceServicer_to_server(
        IrisRuntimeGrpcServicer(runtime_service, mapper=mapper),
        server,
    )


def create_grpc_server(
    runtime_service: IrisRuntimeService,
    *,
    host: str = "127.0.0.1",
    port: int = 50051,
    identity_resolver: IdentityResolver | None = None,
) -> grpc.aio.Server:
    """Create a grpc.aio server with Iris runtime service registered.

    Args:
        runtime_service: Runtime service that handles mapped observations.
        host: Bind host. Defaults to loopback.
        port: Bind port. Defaults to 50051.
        identity_resolver: Optional resolver injected into the gRPC mapper.

    Returns:
        grpc.aio.Server: Configured but not started server.

    Raises:
        RuntimeError: If port binding fails.
    """
    server = grpc.aio.server()
    add_iris_runtime_servicer(server, runtime_service, identity_resolver=identity_resolver)
    bound_port = server.add_insecure_port(f"{host}:{port}")
    if bound_port == 0:
        message = f"failed to bind gRPC port {host}:{port}"
        raise RuntimeError(message)
    return server
