"""Tests for Device contracts."""

from __future__ import annotations

from iris.contracts.devices import DeviceCapability, DeviceKind, DeviceProfile
from iris.core.ids import ActorId, DeviceId
from tests.helpers.immutability import assert_frozen_field
from tests.helpers.mapping import assert_mapping_rejects_item_assignment


def test_device_profile_stores_kind_and_capabilities() -> None:
    """DeviceProfile stores device kind and capabilities."""
    capability = DeviceCapability(name="audio_input", metadata={"sample_rate": "48000"})
    profile = DeviceProfile(
        device_id=DeviceId("device-1"),
        device_kind=DeviceKind.MICROPHONE,
        display_name="Desk Mic",
        owner_actor_id=ActorId("actor-1"),
        capabilities=(capability,),
        metadata={"room": "studio"},
    )

    assert profile.device_id == DeviceId("device-1")
    assert profile.device_kind is DeviceKind.MICROPHONE
    assert profile.owner_actor_id == ActorId("actor-1")
    assert profile.capabilities == (capability,)
    assert profile.capabilities[0].metadata["sample_rate"] == "48000"
    assert profile.metadata["room"] == "studio"


def test_device_profile_is_frozen() -> None:
    """DeviceProfile is immutable."""
    profile = DeviceProfile(
        device_id=DeviceId("device-1"),
        device_kind=DeviceKind.CLIENT,
        display_name="Client",
    )

    assert_frozen_field(profile, "display_name", "Renamed")


def test_device_capability_is_frozen() -> None:
    """DeviceCapability is immutable."""
    capability = DeviceCapability(name="audio_output")

    assert_frozen_field(capability, "name", "renamed")


def test_device_capability_metadata_is_defensively_copied() -> None:
    """DeviceCapability defensively copies metadata."""
    metadata = {"version": "1.0"}
    capability = DeviceCapability(name="audio_input", metadata=metadata)

    metadata["version"] = "2.0"

    assert capability.metadata["version"] == "1.0"
    assert_mapping_rejects_item_assignment(capability.metadata)


def test_device_profile_metadata_is_defensively_copied() -> None:
    """DeviceProfile defensively copies metadata."""
    metadata = {"os": "linux"}
    profile = DeviceProfile(
        device_id=DeviceId("device-1"),
        device_kind=DeviceKind.MICROPHONE,
        display_name="Desk Mic",
        metadata=metadata,
    )

    metadata["os"] = "changed"

    assert profile.metadata["os"] == "linux"
    assert_mapping_rejects_item_assignment(profile.metadata)
