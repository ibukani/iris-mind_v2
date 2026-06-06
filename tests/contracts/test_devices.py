"""Tests for Device contracts."""
from __future__ import annotations

import pytest

from iris.contracts.devices import DeviceCapability, DeviceKind, DeviceProfile
from iris.core.ids import DeviceId


def test_device_capability_metadata_is_defensively_copied() -> None:
    """DeviceCapability defensively copies metadata."""
    metadata = {"version": "1.0"}
    capability = DeviceCapability(name="audio", metadata=metadata)

    metadata["version"] = "2.0"

    assert capability.metadata["version"] == "1.0"
    with pytest.raises(TypeError):
        capability.metadata["new"] = "value"  # type: ignore[index]  # testing immutability


def test_device_profile_metadata_is_defensively_copied() -> None:
    """DeviceProfile defensively copies metadata."""
    metadata = {"os": "linux"}
    profile = DeviceProfile(
        device_id=DeviceId("dev-1"),
        device_kind=DeviceKind.CLIENT,
        display_name="Home PC",
        metadata=metadata,
    )

    metadata["os"] = "windows"

    assert profile.metadata["os"] == "linux"
    with pytest.raises(TypeError):
        profile.metadata["new"] = "value"  # type: ignore[index]  # testing immutability
