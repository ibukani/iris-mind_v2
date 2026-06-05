"""Explicit gRPC runtime server wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING

import grpc

from iris.adapters.grpc.server import IrisRuntimeGrpcServicer
from iris.generated.iris.runtime.v1 import runtime_pb2_grpc

if TYPE_CHECKING:
    from iris.runtime.service import IrisRuntimeService


def add_iris_runtime_servicer(
    server: grpc.aio.Server,
    runtime_service: IrisRuntimeService,
) -> None:
    """Register IrisRuntimeGrpcServicer on a gRPC aio server."""
    runtime_pb2_grpc.add_IrisRuntimeServiceServicer_to_server(
        IrisRuntimeGrpcServicer(runtime_service),
        server,
    )


def create_grpc_server(
    runtime_service: IrisRuntimeService,
    *,
    host: str = "127.0.0.1",
    port: int = 50051,
) -> grpc.aio.Server:
    """Create a grpc.aio server with Iris runtime service registered.

    Returns:
        grpc.aio.Server: Configured but not started server.

    Raises:
        RuntimeError: If port binding fails.
    """
    server = grpc.aio.server()
    add_iris_runtime_servicer(server, runtime_service)
    bound_port = server.add_insecure_port(f"{host}:{port}")
    if bound_port == 0:
        message = f"failed to bind gRPC port {host}:{port}"
        raise RuntimeError(message)
    return server
