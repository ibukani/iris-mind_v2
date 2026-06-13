"""Tests for shared external reference DTOs."""

from __future__ import annotations

from types import MappingProxyType

from iris.contracts.external_refs import ExternalAccountRef, ExternalSpaceRef
from iris.contracts.identity import ActorKind
from iris.contracts.spaces import SpaceKind
from iris.core.ids import ExternalRef


def test_external_account_ref_metadata_is_defensively_copied() -> None:
    """ExternalAccountRef defensively copies metadata into an immutable mapping proxy."""
    mutable_dict = {"key": "value"}
    ref = ExternalAccountRef(
        provider="discord",
        provider_subject=ExternalRef("123"),
        display_name="User",
        metadata=mutable_dict,
    )

    assert isinstance(ref.metadata, MappingProxyType)
    assert ref.metadata == {"key": "value"}

    # Mutating original dict shouldn't affect the ref
    mutable_dict["key"] = "changed"
    assert ref.metadata["key"] == "value"


def test_external_account_ref_default_actor_kind() -> None:
    """ExternalAccountRef defaults to ActorKind.HUMAN."""
    ref = ExternalAccountRef(
        provider="discord",
        provider_subject=ExternalRef("123"),
        display_name="User",
    )

    assert ref.actor_kind == ActorKind.HUMAN


def test_external_space_ref_metadata_is_defensively_copied() -> None:
    """ExternalSpaceRef defensively copies metadata into an immutable mapping proxy."""
    mutable_dict = {"channel": "general"}
    ref = ExternalSpaceRef(
        provider="discord",
        provider_space_ref=ExternalRef("456"),
        display_name="Server",
        space_kind=SpaceKind.TEXT_CHANNEL,
        metadata=mutable_dict,
    )

    assert isinstance(ref.metadata, MappingProxyType)
    assert ref.metadata == {"channel": "general"}

    # Mutating original dict shouldn't affect the ref
    mutable_dict["channel"] = "random"
    assert ref.metadata["channel"] == "general"
