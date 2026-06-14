"""Tests for Observations contracts."""

from __future__ import annotations

from datetime import UTC, datetime

from iris.contracts.activity import ActivityKind
from iris.contracts.observations import (
    ActivityEventObservation,
    ObservationContext,
    ObservationKind,
    PresenceSignalObservation,
)
from iris.contracts.presence import PresenceStatus
from iris.core.ids import AccountId, ObservationId, SessionId
from tests.helpers.mapping import assert_mapping_rejects_item_assignment


def test_observation_context_metadata_is_defensively_copied() -> None:
    """ObservationContext defensively copies metadata."""
    metadata = {"mood": "happy"}
    context = ObservationContext(
        account_id=AccountId("acc-1"),
        metadata=metadata,
    )

    metadata["mood"] = "sad"

    assert context.metadata["mood"] == "happy"
    assert_mapping_rejects_item_assignment(context.metadata)


def test_observation_kind_exposes_only_typed_ingress_kinds() -> None:
    """ObservationKindが実装済みtyped ingressだけを持つことを確認する。"""
    assert {kind.value for kind in ObservationKind} == {
        "actor_message",
        "idle_tick",
        "activity_event",
        "presence_signal",
    }


def test_activity_event_observation_carries_typed_fields_and_frozen_metadata() -> None:
    """ActivityEventObservationがtyped fieldsと不変metadataを持つことを確認する。"""
    metadata = {"gateway_shard_id": "2"}
    observation = ActivityEventObservation(
        observation_id=ObservationId("obs-activity"),
        session_id=SessionId("session-1"),
        context=ObservationContext(),
        occurred_at=datetime(2026, 6, 13, tzinfo=UTC),
        kind=ObservationKind.ACTIVITY_EVENT,
        activity_kind=ActivityKind.VOICE_JOINED,
        provider_event_id="event-1",
        provider_sequence=42,
        metadata=metadata,
    )

    metadata["gateway_shard_id"] = "3"

    assert observation.activity_kind is ActivityKind.VOICE_JOINED
    assert observation.provider_event_id == "event-1"
    assert observation.provider_sequence == 42
    assert observation.metadata == {"gateway_shard_id": "2"}
    assert_mapping_rejects_item_assignment(observation.metadata)


def test_presence_signal_observation_carries_expiry_and_frozen_metadata() -> None:
    """PresenceSignalObservationがstatus、expires_at、不変metadataを持つことを確認する。"""
    expires_at = datetime(2026, 6, 13, 1, tzinfo=UTC)
    metadata = {"client_name": "desktop"}
    observation = PresenceSignalObservation(
        observation_id=ObservationId("obs-presence"),
        session_id=SessionId("session-1"),
        context=ObservationContext(),
        occurred_at=datetime(2026, 6, 13, tzinfo=UTC),
        kind=ObservationKind.PRESENCE_SIGNAL,
        status=PresenceStatus.AWAY,
        expires_at=expires_at,
        metadata=metadata,
    )

    metadata["client_name"] = "mobile"

    assert observation.status is PresenceStatus.AWAY
    assert observation.expires_at == expires_at
    assert observation.metadata == {"client_name": "desktop"}
    assert_mapping_rejects_item_assignment(observation.metadata)
