"""AccountStore-backed IdentityResolver."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, override

from iris.adapters.app_gateway.ports import IdentityResolver
from iris.adapters.app_gateway.stable_ids import stable_account_id, stable_actor_id
from iris.contracts.accounts import AccountProfile
from iris.contracts.identity import Identity

if TYPE_CHECKING:
    from iris.adapters.app_gateway.ports import AccountStore
    from iris.contracts.external_refs import ExternalAccountRef
    from iris.core.ids import DeviceId


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
            resolved_account_id = account_ref.account_id or stable_account_id(
                account_ref.provider, account_ref.provider_subject
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

        # Determine actor_id
        actor_id = profile.linked_actor_id or stable_actor_id(profile.account_id)

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
