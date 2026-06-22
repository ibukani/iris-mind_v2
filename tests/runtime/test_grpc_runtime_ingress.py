"""Runtime gRPC ingress integration tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, override

import grpc
import pytest

from iris.adapters.app_gateway.fake_resolvers import FakeIdentityResolver
from iris.adapters.app_gateway.ports import SpaceResolver
from iris.adapters.grpc.mappers import GrpcRuntimeMapper, timestamp_from_datetime
from iris.adapters.grpc.server import IrisRuntimeGrpcServicer
from iris.contracts.spaces import InteractionSpace
from iris.core.ids import SpaceId
from iris.generated.iris.api.v1 import identity_pb2, observations_pb2, spaces_pb2
from iris.generated.iris.runtime.v1 import runtime_pb2, runtime_pb2_grpc
from iris.runtime.service import IrisRuntimeService, RuntimeResponse
from tests.helpers.grpc_test import RecordingRuntimeService, grpc_call

if TYPE_CHECKING:
    from types import TracebackType

    from iris.adapters.app_gateway.ports import IdentityResolver
    from iris.contracts.external_refs import ExternalSpaceRef
    from iris.runtime.service import ObservationEnvelope


_AsyncSubmitObservation = Callable[
    [runtime_pb2.SubmitObservationRequest],
    Awaitable[runtime_pb2.SubmitObservationResponse],
]

_OCCURRED_AT = datetime(2026, 6, 5, 13, 0, tzinfo=UTC)


@pytest.mark.anyio
async def test_submit_observation_returns_presented_output() -> None:
    """SubmitObservationがRuntimeServiceへ委譲しPresentedOutputを返すことを確認する。"""
    runtime_service = RecordingRuntimeService("grpc response")

    async with _GrpcRuntimeHarness(runtime_service) as stub:
        response = await grpc_call(stub.SubmitObservation(_actor_message_request()))
        assert isinstance(response, runtime_pb2.SubmitObservationResponse)
    assert runtime_service.envelope is not None
    assert runtime_service.envelope.observation.kind.value == "actor_message"
    assert runtime_service.envelope.ingress.authenticated
    assert runtime_service.envelope.ingress.capabilities == frozenset(
        {
            "integrate_activity",
            "integrate_presence",
            "update_space_occupancy",
            "react_to_activity",
            "internal_event",
            "register_delivery_target",
        }
    )
    assert response.correlation_id == "corr-1"
    assert response.output.text == "grpc response"


@pytest.mark.anyio
async def test_submit_observation_invalid_request_returns_invalid_argument() -> None:
    """Invalid proto inputがINVALID_ARGUMENTになることを確認する。"""
    async with _GrpcRuntimeHarness(RecordingRuntimeService("unused")) as stub:
        coro = stub.SubmitObservation(
            runtime_pb2.SubmitObservationRequest(
                correlation_id="corr-1",
                observation=observations_pb2.Observation(
                    observation_id="obs-1",
                    session_id="session-1",
                    kind=observations_pb2.OBSERVATION_KIND_UNSPECIFIED,
                    occurred_at=timestamp_from_datetime(_OCCURRED_AT),
                ),
            )
        )
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await grpc_call(coro)

    assert exc_info.value.code() is grpc.StatusCode.INVALID_ARGUMENT


@pytest.mark.anyio
async def test_submit_observation_runtime_failure_returns_internal() -> None:
    """Runtime service failureがINTERNALになることを確認する。"""
    async with _GrpcRuntimeHarness(_FailingRuntimeService()) as stub:
        coro = stub.SubmitObservation(_actor_message_request())
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await grpc_call(coro)

    assert exc_info.value.code() is grpc.StatusCode.INTERNAL


@pytest.mark.anyio
async def test_submit_observation_with_account_ref_resolves_identity() -> None:
    """account_refを持つSubmitObservationがgRPC境界でIdentityへ解決されることを確認する。"""
    runtime_service = RecordingRuntimeService("account_ref response")
    resolver = FakeIdentityResolver()

    async with _GrpcRuntimeHarness(runtime_service, identity_resolver=resolver) as stub:
        response = await grpc_call(stub.SubmitObservation(_account_ref_request()))
        assert isinstance(response, runtime_pb2.SubmitObservationResponse)
    assert response.output.text == "account_ref response"
    assert runtime_service.envelope is not None
    actor = runtime_service.envelope.observation.context.actor
    assert actor is not None
    assert actor.provider == "discord"
    assert actor.display_name == "Mina"


@pytest.mark.anyio
async def test_submit_observation_account_ref_without_resolver_is_invalid_argument() -> None:
    """resolver未注入でaccount_refを使うとINVALID_ARGUMENTになることを確認する。"""
    async with _GrpcRuntimeHarness(RecordingRuntimeService("unused")) as stub:
        coro = stub.SubmitObservation(_account_ref_request())
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await grpc_call(coro)

    assert exc_info.value.code() is grpc.StatusCode.INVALID_ARGUMENT


@pytest.mark.anyio
async def test_submit_observation_with_actor_and_account_ref_returns_invalid_argument() -> None:
    """actorとaccount_refの両方が設定された場合にINVALID_ARGUMENTになることを確認する。"""
    resolver = FakeIdentityResolver()
    request = runtime_pb2.SubmitObservationRequest(
        correlation_id="corr-1",
        observation=observations_pb2.Observation(
            observation_id="obs-1",
            session_id="session-1",
            kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
            occurred_at=timestamp_from_datetime(_OCCURRED_AT),
            context=observations_pb2.ObservationContext(
                actor=identity_pb2.Identity(
                    actor_id="actor-1",
                    actor_kind=identity_pb2.ACTOR_KIND_HUMAN,
                    display_name="Mina",
                    provider="test",
                    provider_subject="provider-actor-1",
                ),
                account_ref=identity_pb2.ExternalAccountRef(
                    provider="discord",
                    provider_subject="12345",
                    display_name="Mina",
                ),
            ),
            actor_message=observations_pb2.ActorMessagePayload(text="hello grpc"),
        ),
    )

    async with _GrpcRuntimeHarness(
        RecordingRuntimeService("unused"), identity_resolver=resolver
    ) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await grpc_call(stub.SubmitObservation(request))

    assert exc_info.value.code() is grpc.StatusCode.INVALID_ARGUMENT


@pytest.mark.anyio
async def test_submit_observation_account_ref_and_account_id_is_invalid() -> None:
    """account_refとaccount_idの両方が設定された場合にINVALID_ARGUMENTになることを確認する。"""
    request = runtime_pb2.SubmitObservationRequest(
        correlation_id="corr-1",
        observation=observations_pb2.Observation(
            observation_id="obs-1",
            session_id="session-1",
            kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
            occurred_at=timestamp_from_datetime(_OCCURRED_AT),
            context=observations_pb2.ObservationContext(
                account_ref=identity_pb2.ExternalAccountRef(
                    provider="discord",
                    provider_subject="12345",
                    display_name="Mina",
                ),
                account_id="account-1",
            ),
            actor_message=observations_pb2.ActorMessagePayload(text="hello grpc"),
        ),
    )

    async with _GrpcRuntimeHarness(
        RecordingRuntimeService("unused"), identity_resolver=FakeIdentityResolver()
    ) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await grpc_call(stub.SubmitObservation(request))

    assert exc_info.value.code() is grpc.StatusCode.INVALID_ARGUMENT


@pytest.mark.anyio
async def test_submit_observation_with_space_ref_resolves_space() -> None:
    """space_refを持つSubmitObservationがgRPC境界でInteractionSpaceへ解決されることを確認する。"""
    runtime_service = RecordingRuntimeService("space_ref response")
    resolver = _RecordingSpaceResolver()

    async with _GrpcRuntimeHarness(runtime_service, space_resolver=resolver) as stub:
        response = await grpc_call(stub.SubmitObservation(_space_ref_request()))
        assert isinstance(response, runtime_pb2.SubmitObservationResponse)
    assert response.output.text == "space_ref response"
    assert runtime_service.envelope is not None
    assert runtime_service.envelope.observation.context.space_id == "resolved-space-discord-chan-1"


@pytest.mark.anyio
async def test_submit_observation_space_ref_without_resolver_is_invalid_argument() -> None:
    """space_resolver未注入でspace_refを使うとINVALID_ARGUMENTになることを確認する。"""
    async with _GrpcRuntimeHarness(RecordingRuntimeService("unused")) as stub:
        coro = stub.SubmitObservation(_space_ref_request())
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await grpc_call(coro)

    assert exc_info.value.code() is grpc.StatusCode.INVALID_ARGUMENT


@pytest.mark.anyio
async def test_submit_observation_with_space_ref_and_space_id_returns_invalid_argument() -> None:
    """space_refとspace_idの両方が設定された場合にINVALID_ARGUMENTになることを確認する。"""
    resolver = _RecordingSpaceResolver()
    request = _space_ref_request()
    request.observation.context.space_id = "space-existing"

    async with _GrpcRuntimeHarness(
        RecordingRuntimeService("unused"), space_resolver=resolver
    ) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await grpc_call(stub.SubmitObservation(request))

    assert exc_info.value.code() is grpc.StatusCode.INVALID_ARGUMENT


@pytest.mark.anyio
async def test_submit_observation_with_account_ref_and_space_ref_succeeds() -> None:
    """account_refとspace_refの両方が設定され、両方のresolverが注入されている場合に成功することを確認する。"""
    id_resolver = FakeIdentityResolver()
    space_resolver = _RecordingSpaceResolver()
    runtime_service = RecordingRuntimeService("both response")

    request = _space_ref_request()
    request.observation.context.account_ref.CopyFrom(
        identity_pb2.ExternalAccountRef(
            provider="discord",
            provider_subject="12345",
            display_name="Mina",
        )
    )

    async with _GrpcRuntimeHarness(
        runtime_service,
        identity_resolver=id_resolver,
        space_resolver=space_resolver,
    ) as stub:
        response = await grpc_call(stub.SubmitObservation(request))
        assert isinstance(response, runtime_pb2.SubmitObservationResponse)
    assert response.output.text == "both response"
    assert runtime_service.envelope is not None
    assert runtime_service.envelope.observation.context.space_id == "resolved-space-discord-chan-1"
    assert runtime_service.envelope.observation.context.actor is not None
    assert runtime_service.envelope.observation.context.actor.display_name == "Mina"


@pytest.mark.anyio
async def test_get_runtime_info_returns_supported_features() -> None:
    """GetRuntimeInfoがサポートする機能とバージョン情報を返すことを確認する。"""
    async with _GrpcRuntimeHarness(RecordingRuntimeService("unused")) as stub:
        request = runtime_pb2.GetRuntimeInfoRequest()
        response = await grpc_call(stub.GetRuntimeInfo(request))
        assert isinstance(response, runtime_pb2.GetRuntimeInfoResponse)

    assert response.runtime_name == "iris-mind"
    assert response.runtime_version == "0.1.0"
    assert response.api_version == "iris.runtime.v1"
    assert "submit_observation" in response.supported_features
    assert "persistent_account" in response.supported_features
    assert "ephemeral_space" in response.supported_features
    assert "poll_app_actions" not in response.supported_features
    assert "report_action_result" not in response.supported_features


@pytest.mark.anyio
async def test_submit_observation_with_cli_like_request_succeeds() -> None:
    """CLI想定のSubmitObservationリクエストが正しく受け付けられることを確認する。"""
    id_resolver = FakeIdentityResolver()
    space_resolver = _RecordingSpaceResolver()
    runtime_service = RecordingRuntimeService("cli response")

    request = runtime_pb2.SubmitObservationRequest(
        correlation_id="cli-req-1",
        observation=observations_pb2.Observation(
            observation_id="cli-obs-1",
            session_id="cli-session-1",
            kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
            occurred_at=timestamp_from_datetime(_OCCURRED_AT),
            context=observations_pb2.ObservationContext(
                source="cli",
                account_ref=identity_pb2.ExternalAccountRef(
                    provider="cli",
                    provider_subject="local-user",
                    display_name="CLI User",
                    actor_kind=identity_pb2.ACTOR_KIND_HUMAN,
                ),
                space_ref=spaces_pb2.ExternalSpaceRef(
                    provider="cli",
                    provider_space_ref="session:cli-session-1",
                    display_name="CLI session",
                    space_kind=spaces_pb2.SPACE_KIND_DIRECT_MESSAGE,
                ),
            ),
            actor_message=observations_pb2.ActorMessagePayload(
                text="hello",
                external_message_id="cli-message-1",
            ),
        ),
    )

    async with _GrpcRuntimeHarness(
        runtime_service,
        identity_resolver=id_resolver,
        space_resolver=space_resolver,
    ) as stub:
        response = await grpc_call(stub.SubmitObservation(request))
        assert isinstance(response, runtime_pb2.SubmitObservationResponse)

    assert response.correlation_id == "cli-req-1"
    assert response.output.text == "cli response"

    assert runtime_service.envelope is not None
    ctx = runtime_service.envelope.observation.context
    assert ctx.source == "cli"

    actor = ctx.actor
    assert actor is not None
    assert actor.provider == "cli"
    assert actor.provider_subject == "local-user"

    space_id = ctx.space_id
    assert space_id == "resolved-space-cli-session:cli-session-1"


def _actor_message_request() -> runtime_pb2.SubmitObservationRequest:
    """ActorMessage SubmitObservationRequest fixtureを作る。

    Returns:
        runtime_pb2.SubmitObservationRequest: Actor message request DTO。
    """
    return runtime_pb2.SubmitObservationRequest(
        correlation_id="corr-1",
        observation=observations_pb2.Observation(
            observation_id="obs-1",
            session_id="session-1",
            kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
            occurred_at=timestamp_from_datetime(_OCCURRED_AT),
            actor_message=observations_pb2.ActorMessagePayload(text="hello grpc"),
        ),
    )


def _account_ref_request() -> runtime_pb2.SubmitObservationRequest:
    """account_ref付きActorMessage SubmitObservationRequest fixtureを作る。

    Returns:
        runtime_pb2.SubmitObservationRequest: Actor message request DTO with account_ref。
    """
    return runtime_pb2.SubmitObservationRequest(
        correlation_id="corr-1",
        observation=observations_pb2.Observation(
            observation_id="obs-1",
            session_id="session-1",
            kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
            occurred_at=timestamp_from_datetime(_OCCURRED_AT),
            context=observations_pb2.ObservationContext(
                account_ref=identity_pb2.ExternalAccountRef(
                    provider="discord",
                    provider_subject="12345",
                    display_name="Mina",
                ),
            ),
            actor_message=observations_pb2.ActorMessagePayload(text="hello grpc"),
        ),
    )


def _space_ref_request() -> runtime_pb2.SubmitObservationRequest:
    """space_ref付きActorMessage SubmitObservationRequest fixtureを作る。

    Returns:
        runtime_pb2.SubmitObservationRequest: Actor message request DTO with space_ref。
    """
    return runtime_pb2.SubmitObservationRequest(
        correlation_id="corr-1",
        observation=observations_pb2.Observation(
            observation_id="obs-1",
            session_id="session-1",
            kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
            occurred_at=timestamp_from_datetime(_OCCURRED_AT),
            context=observations_pb2.ObservationContext(
                space_ref=spaces_pb2.ExternalSpaceRef(
                    provider="discord",
                    provider_space_ref="chan-1",
                    display_name="General",
                    space_kind=spaces_pb2.SPACE_KIND_TEXT_CHANNEL,
                ),
            ),
            actor_message=observations_pb2.ActorMessagePayload(text="hello grpc"),
        ),
    )


class _FailingRuntimeService(IrisRuntimeService):
    """Fake runtime service that raises to exercise INTERNAL mapping."""

    def __init__(self) -> None:
        """Initialize failing service recording slot."""
        self.envelope: ObservationEnvelope | None = None

    @override
    async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
        """Raise a runtime failure.

        Raises:
            RuntimeError: Always raised for test.
        """
        self.envelope = envelope
        message = "boom"
        raise RuntimeError(message)


class _GrpcRuntimeHarness:
    """Async context manager for an in-process grpc.aio test server."""

    def __init__(
        self,
        runtime_service: IrisRuntimeService,
        *,
        identity_resolver: IdentityResolver | None = None,
        space_resolver: SpaceResolver | None = None,
    ) -> None:
        """Create harness around a fake runtime service."""
        self._runtime_service = runtime_service
        self._identity_resolver = identity_resolver
        self._space_resolver = space_resolver
        self._server: grpc.aio.Server | None = None
        self._channel: grpc.aio.Channel | None = None

    async def __aenter__(self) -> runtime_pb2_grpc.IrisRuntimeServiceAsyncStub:
        """Start server and return a connected stub.

        Returns:
            runtime_pb2_grpc.IrisRuntimeServiceAsyncStub: Connected gRPC stub.
        """
        server = grpc.aio.server()
        mapper = GrpcRuntimeMapper(
            identity_resolver=self._identity_resolver,
            space_resolver=self._space_resolver,
        )
        runtime_pb2_grpc.add_IrisRuntimeServiceServicer_to_server(
            IrisRuntimeGrpcServicer(self._runtime_service, mapper=mapper),
            server,
        )
        port = server.add_insecure_port("127.0.0.1:0")
        await server.start()
        channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
        self._server = server
        self._channel = channel
        return runtime_pb2_grpc.IrisRuntimeServiceStub(channel)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close client channel and stop server."""
        _ = exc_type, exc, traceback
        if self._channel is not None:
            await self._channel.close()
        if self._server is not None:
            await self._server.stop(0)


class _RecordingSpaceResolver(SpaceResolver):
    """Fake SpaceResolver that returns deterministic space."""

    @override
    async def resolve_space(
        self,
        space_ref: ExternalSpaceRef,
    ) -> InteractionSpace:
        return InteractionSpace(
            space_id=SpaceId(f"resolved-space-{space_ref.provider}-{space_ref.provider_space_ref}"),
            space_kind=space_ref.space_kind,
            display_name=space_ref.display_name,
            metadata=dict(space_ref.metadata),
        )
