"""明示的な gRPC ランタイムサーバーのワイヤリング。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import grpc

from iris.adapters.grpc.mappers import GrpcRuntimeMapper, RuntimeIngressProfile
from iris.adapters.grpc.server import IrisRuntimeGrpcServicer
from iris.generated.iris.runtime.v1 import runtime_pb2_grpc
from iris.runtime.ingress.observation_ingress import ObservationCapability

if TYPE_CHECKING:
    from collections.abc import Iterable

    from iris.adapters.app_gateway.ports import AppActionBroker, IdentityResolver, SpaceResolver
    from iris.runtime.service import IrisRuntimeService


def add_iris_runtime_servicer(
    server: grpc.aio.Server,
    runtime_service: IrisRuntimeService,
    *,
    app_action_broker: AppActionBroker | None = None,
    identity_resolver: IdentityResolver | None = None,
    space_resolver: SpaceResolver | None = None,
    ingress_profile: RuntimeIngressProfile = RuntimeIngressProfile.EXTERNAL_CLIENT,
    adapter_capabilities: Iterable[ObservationCapability] | None = None,
) -> None:
    """IrisRuntimeGrpcServicer を gRPC aio サーバーに登録する。"""
    mapper = GrpcRuntimeMapper(
        identity_resolver=identity_resolver,
        space_resolver=space_resolver,
        ingress_profile=ingress_profile,
        adapter_capabilities=adapter_capabilities,
    )
    runtime_pb2_grpc.add_IrisRuntimeServiceServicer_to_server(
        IrisRuntimeGrpcServicer(
            runtime_service,
            app_action_broker=app_action_broker,
            mapper=mapper,
        ),
        server,
    )


def create_grpc_server(
    runtime_service: IrisRuntimeService,
    *,
    host: str = "127.0.0.1",
    port: int = 50051,
    app_action_broker: AppActionBroker | None = None,
    identity_resolver: IdentityResolver | None = None,
    space_resolver: SpaceResolver | None = None,
    ingress_profile: RuntimeIngressProfile = RuntimeIngressProfile.EXTERNAL_CLIENT,
    adapter_capabilities: Iterable[ObservationCapability] | None = None,
) -> grpc.aio.Server:
    """GRPC aio server を作成し、Iris runtime servicer を登録する。

    Returns:
        構成済みの gRPC aio server。

    Raises:
        RuntimeError: gRPC port bind に失敗した場合。
    """
    server = grpc.aio.server()
    add_iris_runtime_servicer(
        server,
        runtime_service,
        app_action_broker=app_action_broker,
        identity_resolver=identity_resolver,
        space_resolver=space_resolver,
        ingress_profile=ingress_profile,
        adapter_capabilities=adapter_capabilities,
    )
    bound_port = server.add_insecure_port(f"{host}:{port}")
    if bound_port == 0:
        message = f"failed to bind gRPC port {host}:{port}"
        raise RuntimeError(message)
    return server
