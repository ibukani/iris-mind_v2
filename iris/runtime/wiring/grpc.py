"""明示的な gRPC ランタイムサーバーのワイヤリング。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, Unpack

import grpc
from loguru import logger

from iris.adapters.grpc.auth_interceptor import RuntimeGrpcAuthInterceptor
from iris.adapters.grpc.mappers import GrpcRuntimeMapper, RuntimeIngressProfile
from iris.adapters.grpc.server import IrisRuntimeGrpcServicer
from iris.generated.iris.runtime.v1 import runtime_pb2_grpc
from iris.runtime.config.auth import RuntimeAuthMode

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
    _validate_auth_wiring(auth_config, token_verifier)
    if (
        host not in {"127.0.0.1", "localhost", "::1"}
        and auth_config is not None
        and auth_config.allow_insecure_remote
    ):
        logger.warning(
            "%s %s",
            "server.local_only=false and auth.allow_insecure_remote=true is enabled;",
            "external traffic is allowed insecurely.",
        )

    interceptors: list[grpc.aio.ServerInterceptor] = []
    if auth_config is not None and token_verifier is not None:
        if auth_config.mode is RuntimeAuthMode.REQUIRED and token_verifier.entry_count == 0:
            message = "required auth mode requires at least one static token entry"
            raise RuntimeError(message)
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
        _require_secure_remote_bind(host, auth_config)
        bound_port = server.add_insecure_port(address)
    if bound_port == 0:
        message = f"failed to bind gRPC port {host}:{port}"
        raise RuntimeError(message)
    return server


def _validate_auth_wiring(
    auth_config: RuntimeAuthConfig | None,
    token_verifier: StaticBearerTokenVerifier | None,
) -> None:
    """auth_config と token_verifier の依存関係を先に検証する。

    Raises:
        RuntimeError: 片方だけが指定された場合。
    """
    if auth_config is not None and token_verifier is None:
        message = "auth_config provided without token_verifier"
        raise RuntimeError(message)
    if token_verifier is not None and auth_config is None:
        message = "token_verifier provided without auth_config"
        raise RuntimeError(message)


def _require_secure_remote_bind(host: str, auth_config: RuntimeAuthConfig | None) -> None:
    if (
        host not in {"127.0.0.1", "localhost", "::1"}
        and auth_config is not None
        and auth_config.mode is RuntimeAuthMode.REQUIRED
        and not auth_config.allow_insecure_remote
    ):
        message = "refusing to bind insecure remote gRPC port without allow_insecure_remote=true"
        raise RuntimeError(message)


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
