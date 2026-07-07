"""Interaction activity projection tests。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from iris.contracts.activity import (
    ActivityEventRecord,
    ActivityKind,
    InteractionActivityChannel,
    InteractionActivitySnapshot,
    InteractionModality,
)
from iris.core.ids import AccountId, ActivityId, ActorId, ObservationId, SpaceId
from iris.runtime.ingress.observation_ingress import (
    ObservationCapability,
    ObservationIngressContext,
    trusted_adapter_ingress,
)
from iris.runtime.state.interaction_activity import (
    InMemoryInteractionActivityProjectionStore,
    interaction_snapshot_from_event,
)

_NOW = datetime(2026, 7, 7, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("kind", "channel", "expected_state"),
    [
        (ActivityKind.ACTOR_INPUT_STARTED, InteractionActivityChannel.ACTOR_INPUT, "active"),
        (ActivityKind.ACTOR_INPUT_STOPPED, InteractionActivityChannel.ACTOR_INPUT, "inactive"),
        (ActivityKind.APP_OUTPUT_STARTED, InteractionActivityChannel.APP_OUTPUT, "active"),
        (ActivityKind.APP_OUTPUT_STOPPED, InteractionActivityChannel.APP_OUTPUT, "inactive"),
    ],
)
def test_interaction_event_maps_to_generic_transition(
    kind: ActivityKind,
    channel: InteractionActivityChannel,
    expected_state: str,
) -> None:
    """4種のgeneric eventをchannel別stateへ変換する。"""
    snapshot = interaction_snapshot_from_event(
        _event(kind),
        _ingress(),
        now=_NOW,
        max_ttl_seconds=60,
    )

    assert snapshot is not None
    assert snapshot.channel is channel
    assert snapshot.active is (expected_state == "active")
    assert snapshot.modality is InteractionModality.VOICE
    assert snapshot.reason == "recording"
    assert snapshot.provider == "discord"


@pytest.mark.parametrize(
    "expires_at",
    [None, "invalid", "2026-07-08T12:00:00Z"],
)
def test_interaction_expiry_never_exceeds_server_max_ttl(expires_at: str | None) -> None:
    """missing/invalid/過大expires_atをserver-side max TTLへ制限する。"""
    metadata = {"modality": "voice", "reason": "recording"}
    if expires_at is not None:
        metadata["expires_at"] = expires_at

    snapshot = interaction_snapshot_from_event(
        _event(ActivityKind.ACTOR_INPUT_STARTED, metadata=metadata),
        _ingress(),
        now=_NOW,
        max_ttl_seconds=60,
    )

    assert snapshot is not None
    assert snapshot.expires_at == _NOW + timedelta(seconds=60)


def test_already_expired_advisory_timestamp_does_not_reactivate_state() -> None:
    """過去のvalid expires_atをserver TTLまで延命しない。"""
    snapshot = interaction_snapshot_from_event(
        _event(
            ActivityKind.ACTOR_INPUT_STARTED,
            metadata={"expires_at": "2026-07-07T11:59:00Z"},
        ),
        _ingress(),
        now=_NOW,
        max_ttl_seconds=60,
    )

    assert snapshot is not None
    assert snapshot.expires_at == _NOW


@pytest.mark.anyio
async def test_started_stopped_and_repeated_started_are_idempotent() -> None:
    """Repeated startedは1 stateに収束し、stoppedでinactiveになる。"""
    store = InMemoryInteractionActivityProjectionStore()
    first = interaction_snapshot_from_event(
        _event(ActivityKind.APP_OUTPUT_STARTED),
        _ingress(),
        now=_NOW,
        max_ttl_seconds=60,
    )
    repeated = interaction_snapshot_from_event(
        _event(ActivityKind.APP_OUTPUT_STARTED),
        _ingress(),
        now=_NOW + timedelta(seconds=1),
        max_ttl_seconds=60,
    )
    stopped = interaction_snapshot_from_event(
        _event(ActivityKind.APP_OUTPUT_STOPPED),
        _ingress(),
        now=_NOW + timedelta(seconds=2),
        max_ttl_seconds=60,
    )
    assert first is not None
    assert repeated is not None
    assert stopped is not None

    await store.apply(first)
    await store.apply(repeated)
    assert len(await _active(store, now=_NOW + timedelta(seconds=1))) == 1
    await store.apply(stopped)
    assert await _active(store, now=_NOW + timedelta(seconds=2)) == ()


@pytest.mark.anyio
async def test_expired_state_and_other_space_are_not_returned() -> None:
    """Stale stateを無効化し、provider/space scopeを分離する。"""
    store = InMemoryInteractionActivityProjectionStore()
    current = interaction_snapshot_from_event(
        _event(ActivityKind.ACTOR_INPUT_STARTED),
        _ingress(),
        now=_NOW,
        max_ttl_seconds=30,
    )
    assert current is not None
    await store.apply(current)

    assert await _active(store, now=_NOW + timedelta(seconds=31)) == ()
    assert (
        await store.active_for_target(
            provider="discord",
            actor_id=ActorId("actor-1"),
            account_id=AccountId("account-1"),
            space_id=SpaceId("other-space"),
            now=_NOW,
        )
        == ()
    )


@pytest.mark.anyio
async def test_multiple_adapters_do_not_overwrite_each_other() -> None:
    """同一provider/spaceでもadapter別stateを独立保持する。"""
    store = InMemoryInteractionActivityProjectionStore()
    first = interaction_snapshot_from_event(
        _event(ActivityKind.ACTOR_INPUT_STARTED),
        _ingress(),
        now=_NOW,
        max_ttl_seconds=60,
    )
    second = interaction_snapshot_from_event(
        _event(ActivityKind.ACTOR_INPUT_STARTED),
        trusted_adapter_ingress(
            adapter_id="discord-text-adapter",
            provider="discord",
            capabilities={ObservationCapability.INTEGRATE_ACTIVITY},
        ),
        now=_NOW,
        max_ttl_seconds=60,
    )
    assert first is not None
    assert second is not None

    await store.apply(first)
    await store.apply(second)

    active = await _active(store, now=_NOW)
    assert {snapshot.adapter_id for snapshot in active} == {
        "discord-voice-adapter",
        "discord-text-adapter",
    }
    assert (
        await store.active_for_target(
            provider="slack",
            actor_id=ActorId("actor-1"),
            account_id=AccountId("account-1"),
            space_id=SpaceId("space-1"),
            now=_NOW,
        )
        == ()
    )


def _event(
    kind: ActivityKind,
    *,
    metadata: dict[str, str] | None = None,
) -> ActivityEventRecord:
    return ActivityEventRecord(
        activity_id=ActivityId("activity-1"),
        observation_id=ObservationId("observation-1"),
        provider_event_id="provider-event-1",
        provider_sequence=1,
        actor_id=ActorId("actor-1"),
        account_id=AccountId("account-1"),
        device_id=None,
        space_id=SpaceId("space-1"),
        source="user-controlled-source",
        kind=kind,
        occurred_at=_NOW,
        received_at=_NOW,
        metadata=metadata
        or {
            "modality": "voice",
            "reason": "recording",
            "expires_at": "2026-07-07T12:01:00Z",
        },
    )


def _ingress() -> ObservationIngressContext:
    return trusted_adapter_ingress(
        adapter_id="discord-voice-adapter",
        provider="discord",
        capabilities={ObservationCapability.INTEGRATE_ACTIVITY},
    )


async def _active(
    store: InMemoryInteractionActivityProjectionStore,
    *,
    now: datetime,
) -> tuple[InteractionActivitySnapshot, ...]:
    return await store.active_for_target(
        provider="discord",
        actor_id=ActorId("actor-1"),
        account_id=AccountId("account-1"),
        space_id=SpaceId("space-1"),
        now=now,
    )
