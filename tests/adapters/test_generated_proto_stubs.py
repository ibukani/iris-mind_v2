"""Generated protobuf stub sanity tests."""

from __future__ import annotations

from iris.generated.iris.api.v1 import observations_pb2, spaces_pb2


def test_observation_proto_generated_constants_match_contract() -> None:
    """Observation関連enumの生成済みwire値を確認する。"""
    assert observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE == 1
    assert observations_pb2.OBSERVATION_KIND_IDLE_TICK == 3
    assert observations_pb2.OBSERVATION_KIND_ACTIVITY_EVENT == 6
    assert observations_pb2.OBSERVATION_KIND_PRESENCE_SIGNAL == 7

    assert observations_pb2.ACTIVITY_KIND_ACTOR_TYPING_STARTED == 1
    assert observations_pb2.ACTIVITY_KIND_ACTOR_TYPING_STOPPED == 2
    assert observations_pb2.ACTIVITY_KIND_APP_OPENED == 3
    assert observations_pb2.ACTIVITY_KIND_APP_CLOSED == 4
    assert observations_pb2.ACTIVITY_KIND_VOICE_JOINED == 5
    assert observations_pb2.ACTIVITY_KIND_VOICE_LEFT == 6
    assert observations_pb2.ACTIVITY_KIND_SYSTEM_INTERACTION == 8

    assert observations_pb2.PRESENCE_STATUS_UNKNOWN == 1
    assert observations_pb2.PRESENCE_STATUS_ONLINE == 2
    assert observations_pb2.PRESENCE_STATUS_OFFLINE == 3
    assert observations_pb2.PRESENCE_STATUS_AWAY == 4
    assert observations_pb2.PRESENCE_STATUS_IDLE == 5
    assert observations_pb2.PRESENCE_STATUS_DO_NOT_DISTURB == 6
    assert observations_pb2.PRESENCE_STATUS_INVISIBLE == 7


def test_space_proto_generated_constants_preserve_wire_meanings() -> None:
    """SpaceKindの生成済みwire値を確認する。"""
    assert spaces_pb2.SPACE_KIND_DIRECT_MESSAGE == 1
    assert spaces_pb2.SPACE_KIND_TEXT_CHANNEL == 2
    assert spaces_pb2.SPACE_KIND_THREAD == 3
    assert spaces_pb2.SPACE_KIND_ROOM == 4
    assert spaces_pb2.SPACE_KIND_BROADCAST == 5
    assert spaces_pb2.SPACE_KIND_VOICE_CHANNEL == 6


def test_observation_proto_payload_oneof_names_are_available() -> None:
    """Activity/Presence payloadの生成済みoneof名を確認する。"""
    activity = observations_pb2.Observation(
        kind=observations_pb2.OBSERVATION_KIND_ACTIVITY_EVENT,
        activity_event=observations_pb2.ActivityEventPayload(
            activity_kind=observations_pb2.ACTIVITY_KIND_SYSTEM_INTERACTION,
        ),
    )
    presence = observations_pb2.Observation(
        kind=observations_pb2.OBSERVATION_KIND_PRESENCE_SIGNAL,
        presence_signal=observations_pb2.PresenceSignalPayload(
            status=observations_pb2.PRESENCE_STATUS_ONLINE,
        ),
    )

    assert activity.WhichOneof("payload") == "activity_event"
    assert presence.WhichOneof("payload") == "presence_signal"
