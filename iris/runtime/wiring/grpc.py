"""明示的な gRPC ランタイムサーバーのワイヤリング。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import grpc

from iris.adapters.grpc.mappers import GrpcRuntimeMapper
from iris.adapters.grpc.server import IrisRuntimeGrpcServicer
from iris.generated.iris.runtime.v1 import runtime_pb2_grpc

if TYPE_CHECKING:
    from iris.adapters.app_gateway.ports import IdentityResolver, SpaceResolver
    from iris.runtime.service import IrisRuntimeService


def add_iris_runtime_servicer(
    server: grpc.aio.Server,
    runtime_service: IrisRuntimeService,
    *,
    identity_resolver: IdentityResolver | None = None,
    space_resolver: SpaceResolver | None = None,
) -> None:
    """IrisRuntimeGrpcServicer を gRPC aio サーバーに登録する。

    Args:
        server: servicer を登録する gRPC aio サーバー。
        runtime_service: マッピング済み observation を処理するランタイムサービス。
        identity_resolver: ``ExternalAccountRef`` を型付き ``Identity`` に写像する任意の
            リゾルバ。省略時はマッパーが ``ExternalAccountRef`` 入力を拒否する。
        space_resolver: ``ExternalSpaceRef`` を ``InteractionSpace`` に写像する任意のリゾルバ。
    """
    mapper = GrpcRuntimeMapper(
        identity_resolver=identity_resolver,
        space_resolver=space_resolver,
    )
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
    space_resolver: SpaceResolver | None = None,
) -> grpc.aio.Server:
    """Iris ランタイムサービスを登録した grpc.aio サーバーを生成する。

    Args:
        runtime_service: マッピング済み observation を処理するランタイムサービス。
        host: バインドホスト。デフォルトはループバック。
        port: バインドポート。デフォルトは 50051。
        identity_resolver: gRPC マッパーに注入する任意のリゾルバ。
        space_resolver: gRPC マッパーに注入する任意のリゾルバ。

    Returns:
        grpc.aio.Server: 構成済みだが未起動のサーバー。

    Raises:
        RuntimeError: ポートバインドに失敗した場合。
    """
    server = grpc.aio.server()
    add_iris_runtime_servicer(
        server,
        runtime_service,
        identity_resolver=identity_resolver,
        space_resolver=space_resolver,
    )
    bound_port = server.add_insecure_port(f"{host}:{port}")
    if bound_port == 0:
        message = f"failed to bind gRPC port {host}:{port}"
        raise RuntimeError(message)
    return server
