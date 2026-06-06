"""App Gateway identity and space resolvers."""

from __future__ import annotations

import dataclasses
from hashlib import blake2b
from typing import TYPE_CHECKING, override

from iris.adapters.app_gateway.ports import AccountStore, IdentityResolver, SpaceResolver
from iris.contracts.accounts import AccountProfile
from iris.contracts.identity import Identity
from iris.contracts.spaces import (
    InteractionSpace,
    SpaceParticipant,
    SpaceParticipantKind,
)
from iris.core.ids import AccountId, ActorId, SpaceId

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.adapters.app_gateway.ingress import ExternalAccountRef, ExternalSpaceRef
    from iris.core.ids import DeviceId


def _stable_id(prefix: str, provider: str, external_ref: str) -> str:
    """Generate a short deterministic ID string for resolvers.

    Args:
        prefix: Prefix for the ID (e.g., "actor", "account", "space").
        provider: The provider name.
        external_ref: The external reference from the provider.

    Returns:
        str: A deterministic short ID string.
    """
    digest = blake2b(
        f"{provider}:{external_ref}".encode(),
        digest_size=12,
    ).hexdigest()
    return f"{prefix}-{provider}-{digest}"


def _space_participant(identity: Identity) -> SpaceParticipant:
    """Create a SpaceParticipant snapshot from an Identity.

    Args:
        identity: The identity to snapshot.

    Returns:
        SpaceParticipant: A snapshot of the participant.
    """
    return SpaceParticipant(
        actor_id=identity.actor_id,
        participant_kind=SpaceParticipantKind(identity.actor_kind.value),
        display_name=identity.display_name,
        identity=identity,
    )


class AccountIdentityResolver(IdentityResolver):
    """Identity resolver backed by an AccountStore."""

    def __init__(self, account_store: AccountStore) -> None:
        """Initialize the resolver with an AccountStore.

        Args:
            account_store: Store to persist and lookup accounts.
        """
        self._account_store = account_store

    @override
    async def resolve_identity(
        self,
        account_ref: ExternalAccountRef,
        *,
        device_id: DeviceId | None = None,
    ) -> Identity:
        """Resolve Identity using AccountProfile/AccountStore.

        Returns:
            Identity: Deterministically resolved identity from external ref.
        """
        profile = await self._account_store.get_by_external_ref(
            provider=account_ref.provider,
            provider_subject=account_ref.provider_subject,
        )

        if not profile:
            resolved_account_id = AccountId(
                account_ref.account_id
                or _stable_id("account", account_ref.provider, str(account_ref.provider_subject))
            )
            profile = AccountProfile(
                account_id=resolved_account_id,
                provider=account_ref.provider,
                provider_subject=account_ref.provider_subject,
                display_name=account_ref.display_name,
                metadata=dict(account_ref.metadata),
            )
            profile = await self._account_store.put(profile)
        elif profile.display_name != account_ref.display_name:
            profile = dataclasses.replace(profile, display_name=account_ref.display_name)
            profile = await self._account_store.put(profile)

        if profile.linked_actor_id:
            actor_id = profile.linked_actor_id
        else:
            actor_id = ActorId(_stable_id("actor", "", str(profile.account_id)))

        return Identity(
            actor_id=actor_id,
            actor_kind=account_ref.actor_kind,
            display_name=profile.display_name,
            provider=profile.provider,
            provider_subject=profile.provider_subject,
            account_id=profile.account_id,
            device_id=device_id,
            metadata=dict(profile.metadata),
        )


class EphemeralSpaceResolver(SpaceResolver):
    """Space resolver that generates deterministic spaces without persistence."""

    @override
    async def resolve_space(
        self,
        space_ref: ExternalSpaceRef,
        *,
        participants: Sequence[Identity] = (),
    ) -> InteractionSpace:
        """Return InteractionSpace with a stable SpaceId from provider/provider_space_ref.

        Returns:
            InteractionSpace: Deterministically resolved ephemeral space.
        """
        space_id_str = _stable_id("space", space_ref.provider, str(space_ref.provider_space_ref))
        return InteractionSpace(
            space_id=SpaceId(space_id_str),
            space_kind=space_ref.space_kind,
            display_name=space_ref.display_name,
            participants=tuple(_space_participant(identity) for identity in participants),
            metadata=dict(space_ref.metadata),
        )
