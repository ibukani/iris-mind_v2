"""AccountStore-backed IdentityResolver."""

from __future__ import annotations

from hashlib import blake2b
from typing import TYPE_CHECKING, override

from iris.adapters.app_gateway.ports import IdentityResolver
from iris.contracts.accounts import AccountProfile
from iris.contracts.identity import Identity
from iris.core.ids import AccountId, ActorId

if TYPE_CHECKING:
    from iris.adapters.app_gateway.ingress import ExternalAccountRef
    from iris.adapters.app_gateway.ports import AccountStore
    from iris.core.ids import DeviceId


def _stable_id(prefix: str, provider: str, external_ref: str) -> str:
    """Create a short deterministic ID string.

    Returns:
        str: A deterministic ID prefixed with the given string.
    """
    digest = blake2b(
        f"{provider}:{external_ref}".encode(),
        digest_size=12,
    ).hexdigest()
    return f"{prefix}-{provider}-{digest}"


class AccountBackedIdentityResolver(IdentityResolver):
    """Production identity resolver backed by AccountStore."""

    def __init__(self, account_store: AccountStore) -> None:
        """Initialize with an explicit AccountStore."""
        self._account_store = account_store

    @override
    async def resolve_identity(
        self,
        account_ref: ExternalAccountRef,
        *,
        device_id: DeviceId | None = None,
    ) -> Identity:
        """Resolve Identity using AccountProfile from AccountStore.

        Returns:
            Identity: The resolved identity with deterministic stable IDs.
        """
        # Look up AccountProfile
        profile = await self._account_store.get_by_external_ref(
            provider=account_ref.provider,
            provider_subject=account_ref.provider_subject,
        )

        if not profile:
            # Create a deterministic AccountProfile
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

        # Determine actor_id
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
