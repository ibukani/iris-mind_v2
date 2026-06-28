"""Identityとspace参照のgRPC DTO変換。"""

from __future__ import annotations

from iris.adapters.grpc.mappers.common import metadata_dict, raise_mapping_error
from iris.contracts.external_refs import ExternalAccountRef, ExternalSpaceRef
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.spaces import SpaceKind
from iris.core.ids import AccountId, ActorId, DeviceId, ExternalRef
from iris.generated.iris.api.v1 import identity_pb2, spaces_pb2


def external_account_ref_from_proto(
    account_ref: identity_pb2.ExternalAccountRef,
) -> ExternalAccountRef:
    """ExternalAccountRef protoをcontractへ変換する。

    Returns:
        変換済みExternalAccountRef。
    """
    if not account_ref.provider:
        raise_mapping_error("account_ref.provider is required")
    if not account_ref.provider_subject:
        raise_mapping_error("account_ref.provider_subject is required")
    if not account_ref.display_name:
        raise_mapping_error("account_ref.display_name is required")
    return ExternalAccountRef(
        provider=account_ref.provider,
        provider_subject=ExternalRef(account_ref.provider_subject),
        display_name=account_ref.display_name,
        actor_kind=_account_ref_kind_to_contract(account_ref.actor_kind),
        account_id=None,
        metadata=metadata_dict(account_ref.metadata),
    )


def external_space_ref_from_proto(
    space_ref: spaces_pb2.ExternalSpaceRef,
) -> ExternalSpaceRef:
    """ExternalSpaceRef protoをcontractへ変換する。

    Returns:
        変換済みExternalSpaceRef。
    """
    if not space_ref.provider:
        raise_mapping_error("space_ref.provider is required")
    if not space_ref.provider_space_ref:
        raise_mapping_error("space_ref.provider_space_ref is required")
    if not space_ref.display_name:
        raise_mapping_error("space_ref.display_name is required")
    if space_ref.space_kind == spaces_pb2.SPACE_KIND_UNSPECIFIED:
        raise_mapping_error("space_ref.space_kind must not be unspecified")

    return ExternalSpaceRef(
        provider=space_ref.provider,
        provider_space_ref=ExternalRef(space_ref.provider_space_ref),
        display_name=space_ref.display_name,
        space_kind=_space_kind_from_proto(space_ref.space_kind),
        metadata=metadata_dict(space_ref.metadata),
    )


def identity_from_proto(identity: identity_pb2.Identity) -> Identity:
    """Identity protoをcontractへ変換する。

    Returns:
        変換済みIdentity。
    """
    actor_kind = _actor_kind_from_proto(identity.actor_kind)
    if not identity.actor_id:
        raise_mapping_error("identity.actor_id is required")
    provider = identity.provider or None
    provider_subject = ExternalRef(identity.provider_subject) if identity.provider_subject else None
    if actor_kind not in {ActorKind.SYSTEM, ActorKind.IRIS} and not provider_subject:
        raise_mapping_error("identity.provider_subject is required for external actors")

    return Identity(
        actor_id=ActorId(identity.actor_id),
        actor_kind=actor_kind,
        display_name=identity.display_name,
        provider=provider,
        provider_subject=provider_subject,
        account_id=AccountId(identity.account_id) if identity.account_id else None,
        device_id=DeviceId(identity.device_id) if identity.device_id else None,
        metadata=metadata_dict(identity.metadata),
    )


def _actor_kind_from_proto(kind: identity_pb2.ActorKind.ValueType) -> ActorKind:
    mapping = {
        identity_pb2.ACTOR_KIND_HUMAN: ActorKind.HUMAN,
        identity_pb2.ACTOR_KIND_DEVICE: ActorKind.DEVICE,
        identity_pb2.ACTOR_KIND_SERVICE: ActorKind.SERVICE,
        identity_pb2.ACTOR_KIND_SYSTEM: ActorKind.SYSTEM,
        identity_pb2.ACTOR_KIND_IRIS: ActorKind.IRIS,
    }
    try:
        return mapping[kind]
    except KeyError:
        raise_mapping_error(f"unsupported or unspecified actor kind: {kind}")


def _space_kind_from_proto(kind: spaces_pb2.SpaceKind.ValueType) -> SpaceKind:
    mapping = {
        spaces_pb2.SPACE_KIND_DIRECT_MESSAGE: SpaceKind.DIRECT_MESSAGE,
        spaces_pb2.SPACE_KIND_TEXT_CHANNEL: SpaceKind.TEXT_CHANNEL,
        spaces_pb2.SPACE_KIND_THREAD: SpaceKind.THREAD,
        spaces_pb2.SPACE_KIND_VOICE_CHANNEL: SpaceKind.VOICE_CHANNEL,
        spaces_pb2.SPACE_KIND_ROOM: SpaceKind.ROOM,
        spaces_pb2.SPACE_KIND_BROADCAST: SpaceKind.BROADCAST,
    }
    try:
        return mapping[kind]
    except KeyError:
        raise_mapping_error(f"unsupported or unspecified space kind: {kind}")


def _account_ref_kind_to_contract(kind: identity_pb2.ActorKind.ValueType) -> ActorKind:
    """account_refの未指定actor kindをHUMANとして変換する。

    Returns:
        変換済みActorKind。
    """
    if kind == identity_pb2.ACTOR_KIND_UNSPECIFIED:
        return ActorKind.HUMAN
    return _actor_kind_from_proto(kind)
