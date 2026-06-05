"""Runtime AccountService."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.adapters.app_gateway.ports import AccountStore
    from iris.contracts.accounts import AccountProfile
    from iris.core.ids import AccountId, ActorId, ExternalRef


class AccountService:
    """Internal runtime service for explicit account lookup and linking."""

    def __init__(self, account_store: AccountStore) -> None:
        """Initialize the service with an account store."""
        self._account_store = account_store

    async def get_account_by_id(
        self,
        account_id: AccountId,
    ) -> AccountProfile | None:
        """Get an account profile by its internal AccountId.

        Returns:
            AccountProfile | None: The found account profile, or None.
        """
        return await self._account_store.get_by_account_id(account_id)

    async def get_account_by_external_ref(
        self,
        *,
        provider: str,
        provider_subject: ExternalRef,
    ) -> AccountProfile | None:
        """Get an account profile by provider and subject.

        Returns:
            AccountProfile | None: The found account profile, or None.
        """
        return await self._account_store.get_by_external_ref(
            provider=provider,
            provider_subject=provider_subject,
        )

    async def link_account_to_actor(
        self,
        *,
        account_id: AccountId,
        actor_id: ActorId,
    ) -> AccountProfile:
        """Link an account to an internal ActorId.

        Returns:
            AccountProfile: The updated account profile.
        """
        return await self._account_store.link_account_to_actor(
            account_id=account_id,
            actor_id=actor_id,
        )

    async def unlink_account(
        self,
        account_id: AccountId,
    ) -> AccountProfile:
        """Remove any actor linking from an account.

        Returns:
            AccountProfile: The updated account profile.
        """
        return await self._account_store.unlink_account(account_id)
