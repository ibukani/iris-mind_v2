"""gRPC runtime auth interceptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, override

import grpc

from iris.runtime.auth.context import bind_principal, reset_principal
from iris.runtime.auth.errors import RuntimeUnauthenticatedError
from iris.runtime.auth.principals import local_dev_principal
from iris.runtime.config.auth import RuntimeAuthConfig, RuntimeAuthMode

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from iris.runtime.auth.principals import ClientPrincipal
    from iris.runtime.auth.static_tokens import StaticBearerTokenVerifier

_AUTHORIZATION_KEY = "authorization"


@dataclass(frozen=True)
class RuntimeGrpcAuthInterceptor(grpc.aio.ServerInterceptor):
    """Runtime gRPC bearer token auth interceptor."""

    auth_config: RuntimeAuthConfig
    verifier: StaticBearerTokenVerifier

    @override
    async def intercept_service(
        self,
        continuation: Callable[
            [grpc.HandlerCallDetails],
            Awaitable[grpc.RpcMethodHandler[Any, Any] | None],
        ],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler[Any, Any] | None:
        """RPC handler 実行中に principal context を束縛する。

        Returns:
            principal context を束縛する gRPC method handler。
        """
        handler = await continuation(handler_call_details)
        if handler is None or handler.unary_unary is None:
            return handler
        principal: ClientPrincipal | None = None
        auth_error: RuntimeUnauthenticatedError | None = None
        try:
            principal = self._principal_from_metadata(
                handler_call_details.invocation_metadata,
            )
        except RuntimeUnauthenticatedError as exc:
            auth_error = exc

        bound_unary_unary = handler.unary_unary

        async def _wrapped(request: object, context: grpc.aio.ServicerContext[Any, Any]) -> object:
            if auth_error is not None or principal is None:
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, "unauthenticated")
            token = bind_principal(principal)
            try:
                fn: Any = bound_unary_unary
                return await fn(request, context)
            finally:
                reset_principal(token)

        return grpc.unary_unary_rpc_method_handler(
            _wrapped,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )

    def _principal_from_metadata(
        self,
        metadata: Sequence[tuple[str, str | bytes]] | None,
    ) -> ClientPrincipal:
        """GRPC metadata から ClientPrincipal を取り出す。

        Returns:
            ClientPrincipal: 認証済みまたは local_dev principal。

        Raises:
            RuntimeUnauthenticatedError: 必須 bearer token が不正または欠落した場合。
        """
        authorization = _authorization_from_metadata(metadata)
        if self.auth_config.mode is RuntimeAuthMode.REQUIRED:
            return self.verifier.verify_authorization(authorization)
        if authorization is not None:
            return self.verifier.verify_authorization(authorization)
        if self.auth_config.allow_unauthenticated_loopback:
            return local_dev_principal()
        message = "missing bearer token"
        raise RuntimeUnauthenticatedError(message)


def _authorization_from_metadata(
    metadata: Sequence[tuple[str, str | bytes]] | None,
) -> str | None:
    """GRPC metadata から Authorization ヘッダ値を取り出す。

    Returns:
        Authorization ヘッダ値、なければ None。
    """
    if metadata is None:
        return None
    for key, value in metadata:
        if key.lower() == _AUTHORIZATION_KEY and isinstance(value, str):
            return value
    return None
