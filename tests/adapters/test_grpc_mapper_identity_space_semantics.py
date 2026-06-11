"""gRPC mapper identity and space semantics tests."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from iris.adapters.grpc.mappers import (
    GrpcMappingError,
    external_account_ref_from_proto,
    external_space_ref_from_proto,
    identity_from_proto,
)
from iris.contracts.identity import ActorKind
from iris.contracts.spaces import SpaceKind
from iris.core.ids import ExternalRef
from iris.generated.iris.api.v1 import identity_pb2, spaces_pb2


def test_external_account_ref_maps_domain_fields_and_metadata() -> None:
    """ExternalAccountRef proto maps to domain ref without display_name as ID."""
    ref = external_account_ref_from_proto(
        identity_pb2.ExternalAccountRef(
            provider="discord",
            provider_subject="user-1",
            display_name="Mina",
            actor_kind=identity_pb2.ACTOR_KIND_SERVICE,
            metadata={"role": "bot"},
        )
    )

    assert ref.provider == "discord"
    assert ref.provider_subject == ExternalRef("user-1")
    assert ref.display_name == "Mina"
    assert ref.provider_subject != ExternalRef(ref.display_name)
    assert ref.actor_kind is ActorKind.SERVICE
    assert ref.metadata == {"role": "bot"}
    assert isinstance(ref.metadata, MappingProxyType)


def test_external_space_ref_maps_domain_fields_and_metadata() -> None:
    """ExternalSpaceRef proto maps to domain ref without display_name as ID."""
    ref = external_space_ref_from_proto(
        spaces_pb2.ExternalSpaceRef(
            provider="discord",
            provider_space_ref="channel-1",
            display_name="General",
            space_kind=spaces_pb2.SPACE_KIND_THREAD,
            metadata={"topic": "runtime"},
        )
    )

    assert ref.provider == "discord"
    assert ref.provider_space_ref == ExternalRef("channel-1")
    assert ref.display_name == "General"
    assert ref.provider_space_ref != ExternalRef(ref.display_name)
    assert ref.space_kind is SpaceKind.THREAD
    assert ref.metadata == {"topic": "runtime"}
    assert isinstance(ref.metadata, MappingProxyType)


def test_empty_display_name_is_rejected_for_external_account_ref() -> None:
    """ExternalAccountRef requires explicit display_name."""
    with pytest.raises(GrpcMappingError, match="display_name"):
        external_account_ref_from_proto(
            identity_pb2.ExternalAccountRef(
                provider="discord",
                provider_subject="user-1",
                actor_kind=identity_pb2.ACTOR_KIND_HUMAN,
            )
        )


def test_unspecified_actor_kind_defaults_to_human_for_external_account_ref() -> None:
    """ExternalAccountRef treats unspecified actor_kind as HUMAN."""
    ref = external_account_ref_from_proto(
        identity_pb2.ExternalAccountRef(
            provider="discord",
            provider_subject="user-1",
            display_name="Mina",
            actor_kind=identity_pb2.ACTOR_KIND_UNSPECIFIED,
        )
    )

    assert ref.actor_kind is ActorKind.HUMAN


def test_unspecified_actor_kind_is_rejected_for_direct_identity() -> None:
    """Direct Identity rejects unspecified actor_kind."""
    with pytest.raises(GrpcMappingError, match="actor kind"):
        identity_from_proto(
            identity_pb2.Identity(
                actor_id="actor-1",
                actor_kind=identity_pb2.ACTOR_KIND_UNSPECIFIED,
                display_name="Mina",
                provider="discord",
                provider_subject="user-1",
            )
        )


def test_unspecified_space_kind_is_rejected_for_external_space_ref() -> None:
    """ExternalSpaceRef rejects unspecified space_kind."""
    with pytest.raises(GrpcMappingError, match="space_kind"):
        external_space_ref_from_proto(
            spaces_pb2.ExternalSpaceRef(
                provider="discord",
                provider_space_ref="channel-1",
                display_name="General",
                space_kind=spaces_pb2.SPACE_KIND_UNSPECIFIED,
            )
        )
