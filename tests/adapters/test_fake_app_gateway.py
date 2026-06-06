"""FakeAppGateway tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.adapters.app_gateway.fake_gateway import FakeAppGateway
from iris.adapters.app_gateway.ingress import (
    ActorMessageIngress,
    ActorMessagePayload,
    ExternalAccountRef,
)
from iris.contracts.actions import ActionStatus, AppAction
from iris.core.ids import ActionId, CorrelationId, ExternalRef, SessionId

_CLOCK_AT = datetime(2026, 6, 5, 15, 0, tzinfo=UTC)


@pytest.mark.anyio
async def test_fake_app_gateway_receive_observation_is_fifo() -> None:
    """FakeAppGatewayがingest順にObservationを返すことを確認する。"""
    gateway = FakeAppGateway(clock=lambda: _CLOCK_AT)
    first = await gateway.ingest_actor_message(
        ActorMessageIngress(
            actor=ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("actor-1"),
                display_name="Mina",
            ),
            message=ActorMessagePayload(
                text="first",
                external_message_id=ExternalRef("message-1"),
            ),
            session_id=SessionId("session-1"),
        )
    )
    second = await gateway.ingest_actor_message(
        ActorMessageIngress(
            actor=ExternalAccountRef(
                provider="discord",
                provider_subject=ExternalRef("actor-2"),
                display_name="Nao",
            ),
            message=ActorMessagePayload(
                text="second",
                external_message_id=ExternalRef("message-2"),
            ),
            session_id=SessionId("session-1"),
        )
    )

    assert await gateway.receive_observation() == first
    assert await gateway.receive_observation() == second


@pytest.mark.anyio
async def test_fake_app_gateway_returns_none_when_queue_is_empty() -> None:
    """queueが空のときreceive_observation()がNoneを返すことを確認する。"""
    gateway = FakeAppGateway(clock=lambda: _CLOCK_AT)

    assert await gateway.receive_observation() is None


@pytest.mark.anyio
async def test_fake_app_gateway_execute_returns_deterministic_action_result() -> None:
    """execute()がaction ID/correlation IDを保持した決定論的成功結果を返すことを確認する。"""
    gateway = FakeAppGateway(clock=lambda: _CLOCK_AT)
    action = AppAction(
        action_id=ActionId("action-1"),
        session_id=SessionId("session-1"),
        correlation_id=CorrelationId("correlation-1"),
    )

    result = await gateway.execute(action)

    assert result.action_id == ActionId("action-1")
    assert result.correlation_id == CorrelationId("correlation-1")
    assert result.status == ActionStatus.SUCCEEDED
    assert result.delivered_at == _CLOCK_AT
