"""Tests for Identity contracts."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from iris.contracts.identity import ActorKind, Identity
from iris.core.ids import AccountId, ActorId, DeviceId, ExternalRef
from tests.helpers.immutability import assert_frozen_field
from tests.helpers.mapping import assert_mapping_rejects_item_assignment


def _identity(*, actor_kind: ActorKind, actor_id: str = "actor-1") -> Identity:
    """Build a test Identity for the given actor kind.

    Returns:
        Identity: テスト用のアクター中心のIdentity。
    """
    return Identity(
        actor_id=ActorId(actor_id),
        actor_kind=actor_kind,
        display_name="Test",
        provider="test",
        provider_subject=ExternalRef("subject-1"),
    )


def test_human_identity_carries_account_and_device_optional() -> None:
    """Human Identity is constructible with optional account_id and device_id."""
    identity = _identity(actor_kind=ActorKind.HUMAN)

    assert identity.actor_kind is ActorKind.HUMAN
    assert identity.account_id is None
    assert identity.device_id is None
    assert identity.display_name == "Test"


def test_device_identity_accepts_optional_device_id() -> None:
    """Device Identity accepts a device_id and rejects None for account_id (None still allowed)."""
    identity = Identity(
        actor_id=ActorId("device-1"),
        actor_kind=ActorKind.DEVICE,
        display_name="kitchen-sensor",
        provider="matter",
        provider_subject=ExternalRef("matter://sensor/1"),
        device_id=DeviceId("dev-42"),
    )

    assert identity.actor_kind is ActorKind.DEVICE
    assert identity.device_id == DeviceId("dev-42")
    assert identity.account_id is None


def test_service_identity_carries_account_link() -> None:
    """Service Identity can carry an account_id link without a device_id."""
    identity = Identity(
        actor_id=ActorId("svc-1"),
        actor_kind=ActorKind.SERVICE,
        display_name="scheduler",
        provider="internal",
        provider_subject=ExternalRef("svc-scheduler"),
        account_id=AccountId("acct-1"),
    )

    assert identity.actor_kind is ActorKind.SERVICE
    assert identity.account_id == AccountId("acct-1")


def test_system_identity_uses_system_kind() -> None:
    """System Identity uses ActorKind.SYSTEM with no account or device attached."""
    identity = _identity(actor_kind=ActorKind.SYSTEM, actor_id="system-1")

    assert identity.actor_kind is ActorKind.SYSTEM
    assert identity.actor_id == ActorId("system-1")
    assert identity.account_id is None
    assert identity.device_id is None


def test_iris_identity_uses_iris_kind() -> None:
    """Iris itself is represented as an Identity with ActorKind.IRIS."""
    identity = _identity(actor_kind=ActorKind.IRIS, actor_id="iris-core")

    assert identity.actor_kind is ActorKind.IRIS
    assert identity.actor_id == ActorId("iris-core")


def test_actor_kind_enum_exposes_required_values() -> None:
    """ActorKind must expose human, device, service, system, iris."""
    assert {kind.value for kind in ActorKind} == {"human", "device", "service", "system", "iris"}


@pytest.mark.parametrize("actor_kind", list(ActorKind))
def test_identity_metadata_defaults_to_immutable_empty_mapping(actor_kind: ActorKind) -> None:
    """Identity.metadata defaults to a read-only empty mapping for all actor kinds."""
    identity = _identity(actor_kind=actor_kind)

    assert identity.metadata == MappingProxyType({})


def test_identity_accepts_custom_metadata() -> None:
    """Identity.metadata accepts a custom mapping supplied by the caller."""
    custom = MappingProxyType({"locale": "ja-JP"})
    identity = Identity(
        actor_id=ActorId("actor-1"),
        actor_kind=ActorKind.HUMAN,
        display_name="Mina",
        provider="test",
        provider_subject=ExternalRef("mina"),
        metadata=custom,
    )

    assert identity.metadata == custom
    assert identity.metadata["locale"] == "ja-JP"


def test_identity_is_frozen_dataclass() -> None:
    """Identity is a frozen dataclass — actor_id cannot be reassigned."""
    identity = _identity(actor_kind=ActorKind.HUMAN)

    assert_frozen_field(identity, "actor_id", ActorId("replacement"))


def test_actor_kinds_are_distinct() -> None:
    """Different ActorKind values are distinguishable even with identical other fields."""
    human = Identity(
        actor_id=ActorId("actor-1"),
        actor_kind=ActorKind.HUMAN,
        display_name="Test",
        provider="test",
        provider_subject=ExternalRef("s"),
    )
    device = Identity(
        actor_id=ActorId("actor-1"),
        actor_kind=ActorKind.DEVICE,
        display_name="Test",
        provider="test",
        provider_subject=ExternalRef("s"),
    )

    assert human != device
    assert human.actor_kind != device.actor_kind


def test_identity_metadata_is_defensively_copied() -> None:
    """Identity defensively copies metadata."""
    metadata = {"source": "discord"}
    identity = Identity(
        actor_id=ActorId("actor-1"),
        actor_kind=ActorKind.HUMAN,
        display_name="Mina",
        metadata=metadata,
    )

    metadata["source"] = "changed"

    assert identity.metadata["source"] == "discord"
    assert_mapping_rejects_item_assignment(identity.metadata)
