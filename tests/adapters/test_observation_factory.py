"""ObservationFactory tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.adapters.app_gateway.fake_resolvers import FakeIdentityResolver, FakeSpaceResolver
from iris.adapters.app_gateway.observation_factory import (
    ObservationFactory,
    SequentialObservationIdFactory,
)
from iris.contracts.identity import ActorKind
from iris.contracts.observations import ObservationKind
from iris.contracts.spaces import SpaceKind
from iris.core.ids import AccountId, DeviceId, ExternalRef, ObservationId, SessionId

_OCCURRED_AT = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)
_CLOCK_AT = datetime(2026, 6, 5, 13, 0, tzinfo=UTC)


def _factory() -> ObservationFactory:
    """ObservationFactory test instanceを作る。

    Returns:
        ObservationFactory: fake resolverと固定clockを持つfactory。
    """
    return ObservationFactory(
        identity_resolver=FakeIdentityResolver(),
        space_resolver=FakeSpaceResolver(),
        observation_id_factory=SequentialObservationIdFactory(prefix="test-obs"),
        clock=lambda: _CLOCK_AT,
    )


@pytest.mark.anyio
async def test_observation_factory_resolves_actor_into_context() -> None:
    """resolverが返したIdentityがobservation.context.actorへ入ることを確認する。"""
    observation = await _factory().create_actor_message(
        provider="discord",
        provider_subject=ExternalRef("actor-1"),
        display_name="Mina",
        text="hello",
        session_id=SessionId("session-1"),
        metadata={"mood": "calm"},
    )

    assert observation.observation_id == ObservationId("test-obs-1")
    assert observation.kind == ObservationKind.ACTOR_MESSAGE
    assert observation.context.actor is not None
    assert observation.context.actor.display_name == "Mina"
    assert observation.context.actor.actor_kind == ActorKind.HUMAN
    assert observation.context.actor.provider == "discord"
    assert observation.context.actor.provider_subject == ExternalRef("actor-1")
    assert observation.context.actor.metadata == {"mood": "calm"}
    assert observation.context.metadata == {"mood": "calm"}


@pytest.mark.anyio
async def test_observation_factory_preserves_account_device_source() -> None:
    """account_id/device_id/sourceがObservationContextに保持されることを確認する。"""
    observation = await _factory().create_actor_message(
        provider="discord",
        provider_subject=ExternalRef("actor-1"),
        display_name="Mina",
        text="hello",
        session_id=SessionId("session-1"),
        account_id=AccountId("account-1"),
        device_id=DeviceId("device-1"),
        source="discord-gateway",
    )

    assert observation.context.account_id == AccountId("account-1")
    assert observation.context.device_id == DeviceId("device-1")
    assert observation.context.source == "discord-gateway"


@pytest.mark.anyio
async def test_observation_factory_resolves_space_id_when_ref_present() -> None:
    """provider_space_refがある場合にSpaceResolverのSpaceIdがcontextへ入ることを確認する。"""
    observation = await _factory().create_actor_message(
        provider="discord",
        provider_subject=ExternalRef("actor-1"),
        display_name="Mina",
        text="hello",
        session_id=SessionId("session-1"),
        provider_space_ref=ExternalRef("channel-1"),
        space_display_name="general",
        space_kind=SpaceKind.CHANNEL,
    )
    expected_space = await FakeSpaceResolver().resolve_space(
        provider="discord",
        provider_space_ref=ExternalRef("channel-1"),
        display_name="general",
        space_kind=SpaceKind.CHANNEL,
    )

    assert observation.context.space_id == expected_space.space_id


@pytest.mark.anyio
async def test_observation_factory_leaves_space_id_none_without_space_ref() -> None:
    """provider_space_refがない場合にspace_idがNoneのままであることを確認する。"""
    observation = await _factory().create_actor_message(
        provider="discord",
        provider_subject=ExternalRef("actor-1"),
        display_name="Mina",
        text="hello",
        session_id=SessionId("session-1"),
    )

    assert observation.context.space_id is None


@pytest.mark.anyio
async def test_observation_factory_preserves_message_fields_and_uses_clock() -> None:
    """text/external_message_id/occurred_atの保持とclock fallbackを確認する。"""
    explicit = await _factory().create_actor_message(
        provider="discord",
        provider_subject=ExternalRef("actor-1"),
        display_name="Mina",
        text="hello",
        session_id=SessionId("session-1"),
        occurred_at=_OCCURRED_AT,
        external_message_id=ExternalRef("message-1"),
    )
    fallback = await _factory().create_actor_message(
        provider="discord",
        provider_subject=ExternalRef("actor-1"),
        display_name="Mina",
        text="from clock",
        session_id=SessionId("session-1"),
    )

    assert explicit.text == "hello"
    assert explicit.external_message_id == ExternalRef("message-1")
    assert explicit.occurred_at == _OCCURRED_AT
    assert fallback.text == "from clock"
    assert fallback.occurred_at == _CLOCK_AT
    assert fallback.observation_id == ObservationId("test-obs-1")


def test_sequential_observation_id_factory_is_per_instance_deterministic() -> None:
    """SequentialObservationIdFactoryがinstanceごとの決定論的IDを返すことを確認する。"""
    factory = SequentialObservationIdFactory(prefix="local")

    assert factory() == ObservationId("local-1")
    assert factory() == ObservationId("local-2")
