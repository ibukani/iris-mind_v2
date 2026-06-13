"""Activity contract tests."""

from __future__ import annotations

from datetime import UTC, datetime

from iris.contracts.activity import ActivityKind, ActivityRecord
from iris.core.ids import ActivityId, ObservationId
from tests.helpers.immutability import assert_frozen_field


def test_activity_kind_exposes_non_message_external_events() -> None:
    """ActivityKindがclient-facing非message eventだけを持つことを確認する。"""
    assert {kind.value for kind in ActivityKind} == {
        "actor_typing_started",
        "actor_typing_stopped",
        "app_opened",
        "app_closed",
        "voice_joined",
        "voice_left",
        "system_interaction",
    }


def test_activity_record_is_immutable_and_copies_metadata() -> None:
    """ActivityRecordがimmutable accepted stateであることを確認する。"""
    metadata = {"gateway_shard_id": "1"}
    record = ActivityRecord(
        activity_id=ActivityId("activity:obs-1"),
        observation_id=ObservationId("obs-1"),
        provider_event_id="provider-event-1",
        provider_sequence=2,
        actor_id=None,
        account_id=None,
        device_id=None,
        space_id=None,
        source="internal",
        kind=ActivityKind.SYSTEM_INTERACTION,
        occurred_at=datetime(2026, 6, 13, tzinfo=UTC),
        received_at=datetime(2026, 6, 13, 0, 0, 1, tzinfo=UTC),
        metadata=metadata,
    )

    metadata["gateway_shard_id"] = "2"

    assert record.metadata == {"gateway_shard_id": "1"}
    assert_frozen_field(record, "source", "changed")
