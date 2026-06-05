"""App Gateway identity and space resolvers."""

from __future__ import annotations

from hashlib import blake2b
from typing import TYPE_CHECKING, override

from iris.adapters.app_gateway.ports import AccountStore, IdentityResolver, SpaceResolver
from iris.contracts.accounts import AccountProfile
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.spaces import (
    InteractionSpace,
    SpaceKind,
    SpaceParticipant,
    SpaceParticipantKind,
)
from iris.core.ids import AccountId, ActorId, SpaceId

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from iris.core.ids import DeviceId, ExternalRef


def _stable_id(prefix: str, provider: str, external_ref: str) -> str:
    """Generate a short deterministic ID string for resolvers."""
    digest = blake2b(
        f"{provider}:{external_ref}".encode(),
        digest_size=12,
    ).hexdigest()
    return f"{prefix}-{provider}-{digest}"


def _space_participant(identity: Identity) -> SpaceParticipant:
    """Create a SpaceParticipant snapshot from an Identity."""
    return SpaceParticipant(
        actor_id=identity.actor_id,
        participant_kind=SpaceParticipantKind(identity.actor_kind.value),
        display_name=identity.display_name,
        identity=identity,
    )


class AccountIdentityResolver(IdentityResolver):
    """Identity resolver backed by an AccountStore."""

    def __init__(self, account_store: AccountStore) -> None:
        self._account_store = account_store

    @override
    async def resolve_identity(
        self,
        *,
        provider: str,
        provider_subject: ExternalRef,
        display_name: str,
        actor_kind: ActorKind = ActorKind.HUMAN,
        account_id: AccountId | None = None,
        device_id: DeviceId | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> Identity:
        """Resolve Identity using AccountProfile/AccountStore.

        Returns:
            Identity: Deterministically resolved identity from external ref.
        """
        profile = await self._account_store.get_by_external_ref(
            provider=provider,
            provider_subject=provider_subject,
        )

        if not profile:
            resolved_account_id = AccountId(
                account_id or _stable_id("account", provider, str(provider_subject))
            )
            profile = AccountProfile(
                account_id=resolved_account_id,
                provider=provider,
                provider_subject=provider_subject,
                display_name=display_name,
                metadata=dict(metadata or {}),
            )
            profile = await self._account_store.put(profile)
        elif profile.display_name != display_name:
            import dataclasses

            profile = dataclasses.replace(profile, display_name=display_name)
            profile = await self._account_store.put(profile)

        if profile.linked_actor_id:
            actor_id = profile.linked_actor_id
        else:
            actor_id = ActorId(_stable_id("actor", "", str(profile.account_id)))

        return Identity(
            actor_id=actor_id,
            actor_kind=actor_kind,
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
        *,
        provider: str,
        provider_space_ref: ExternalRef,
        display_name: str,
        space_kind: SpaceKind,
        participants: Sequence[Identity] = (),
        metadata: Mapping[str, str] | None = None,
    ) -> InteractionSpace:
        """Return InteractionSpace with a stable SpaceId from provider/provider_space_ref.

        Returns:
            InteractionSpace: Deterministically resolved ephemeral space.
        """
        return InteractionSpace(
            space_id=SpaceId(_stable_id("space", provider, str(provider_space_ref))),
            space_kind=space_kind,
            display_name=display_name,
            participants=tuple(_space_participant(identity) for identity in participants),
            metadata=dict(metadata or {}),
        )
