"""明示的な gRPC ランタイムサーバーのワイヤリング。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, Unpack

import grpc

from iris.adapters.grpc.auth_interceptor import RuntimeGrpcAuthInterceptor
from iris.adapters.grpc.mappers import GrpcRuntimeMapper, RuntimeIngressProfile
from iris.adapters.grpc.server import IrisRuntimeGrpcServicer
from iris.generated.iris.runtime.v1 import runtime_pb2_grpc

if TYPE_CHECKING:
    from collections.abc import Iterable

    from iris.adapters.app_gateway.ports import AppActionBroker, IdentityResolver, SpaceResolver
    from iris.runtime.auth.policy import RuntimeAuthorizationPolicy
    from iris.runtime.auth.static_tokens import StaticBearerTokenVerifier
    from iris.runtime.config.auth import RuntimeAuthConfig
    from iris.runtime.config.server import RuntimeServerTlsConfig
    from iris.runtime.ingress.observation_ingress import ObservationCapability
    from iris.runtime.service import IrisRuntimeService


class WiringKwargs(TypedDict, total=False):
    """Keyword arguments for gRPC runtime wiring."""

    app_action_broker: AppActionBroker | None
    identity_resolver: IdentityResolver | None
    space_resolver: SpaceResolver | None
    ingress_profile: RuntimeIngressProfile | str
    adapter_capabilities: Iterable[ObservationCapability] | None
    authorization_policy: RuntimeAuthorizationPolicy | None


def add_iris_runtime_servicer(
    server: grpc.aio.Server,
    runtime_service: IrisRuntimeService,
    **kwargs: Unpack[WiringKwargs],
) -> None:
    """IrisRuntimeGrpcServicer を gRPC aio サーバーに登録する。"""
    mapper = GrpcRuntimeMapper(
        identity_resolver=kwargs.get("identity_resolver"),
        space_resolver=kwargs.get("space_resolver"),
        ingress_profile=kwargs.get("ingress_profile", RuntimeIngressProfile.EXTERNAL_CLIENT),
        adapter_capabilities=kwargs.get("adapter_capabilities"),
    )
    runtime_pb2_grpc.add_IrisRuntimeServiceServicer_to_server(
        IrisRuntimeGrpcServicer(
            runtime_service,
            app_action_broker=kwargs.get("app_action_broker"),
            mapper=mapper,
            authorization_policy=kwargs.get("authorization_policy"),
        ),
        server,
    )


def create_grpc_server(
    runtime_service: IrisRuntimeService,
    *,
    host: str = "127.0.0.1",
    port: int = 50051,
    auth_config: RuntimeAuthConfig | None = None,
    token_verifier: StaticBearerTokenVerifier | None = None,
    tls_config: RuntimeServerTlsConfig | None = None,
    **kwargs: Unpack[WiringKwargs],
) -> grpc.aio.Server:
    """GRPC aio server を作成し、Iris runtime servicer を登録する。

    Returns:
        構成済みの gRPC aio server。

    Raises:
        RuntimeError: gRPC port bind に失敗した場合。
    """
    interceptors: list[grpc.aio.ServerInterceptor] = []
    if auth_config is not None and token_verifier is not None:
        interceptors.append(RuntimeGrpcAuthInterceptor(auth_config, token_verifier))
    server = grpc.aio.server(interceptors=interceptors)
    add_iris_runtime_servicer(
        server,
        runtime_service,
        **kwargs,
    )
    address = f"{host}:{port}"
    if tls_config is not None and tls_config.enabled:
        credentials = _server_credentials(tls_config)
        bound_port = server.add_secure_port(address, credentials)
    else:
        bound_port = server.add_insecure_port(address)
    if bound_port == 0:
        message = f"failed to bind gRPC port {host}:{port}"
        raise RuntimeError(message)
    return server


def _server_credentials(tls_config: RuntimeServerTlsConfig) -> grpc.ServerCredentials:
    if tls_config.cert_chain_path is None or tls_config.private_key_path is None:
        message = "TLS certificate chain and private key are required"
        raise RuntimeError(message)
    cert_chain = Path(tls_config.cert_chain_path).read_bytes()
    private_key = Path(tls_config.private_key_path).read_bytes()
    root_certificates = (
        Path(tls_config.client_ca_path).read_bytes()
        if tls_config.client_ca_path is not None
        else None
    )
    return grpc.ssl_server_credentials(
        [(private_key, cert_chain)],
        root_certificates=root_certificates,
        require_client_auth=tls_config.require_client_cert,
    )
