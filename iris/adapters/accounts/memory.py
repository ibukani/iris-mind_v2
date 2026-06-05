"""In-memory account store implementation."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, override

from iris.adapters.app_gateway.ports import AccountStore
from iris.contracts.accounts import AccountStoreError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from iris.contracts.accounts import AccountProfile
    from iris.core.ids import AccountId, ActorId, ExternalRef


class InMemoryAccountStore(AccountStore):
    """In-memory account store for testing and local wiring."""

    def __init__(self, accounts: Iterable[AccountProfile] = ()) -> None:
        """Initialize the store with optional pre-existing accounts."""
        self._accounts_by_id: dict[AccountId, AccountProfile] = {}
        self._accounts_by_ref: dict[tuple[str, str], AccountProfile] = {}

        for account in accounts:
            self._insert_account(account)

    def _insert_account(self, account: AccountProfile) -> None:
        """Insert account without validation (internal)."""
        ref_key = (account.provider, str(account.provider_subject))
        self._accounts_by_id[account.account_id] = account
        self._accounts_by_ref[ref_key] = account

    @override
    async def get_by_external_ref(
        self,
        *,
        provider: str,
        provider_subject: ExternalRef,
    ) -> AccountProfile | None:
        """Get an account profile by provider and subject.

        Returns:
            AccountProfile | None: The found account profile, or None.
        """
        ref_key = (provider, str(provider_subject))
        return self._accounts_by_ref.get(ref_key)

    @override
    async def get_by_account_id(
        self,
        account_id: AccountId,
    ) -> AccountProfile | None:
        """Get an account profile by its internal AccountId.

        Returns:
            AccountProfile | None: The found account profile, or None.
        """
        return self._accounts_by_id.get(account_id)

    @override
    async def put(
        self,
        account: AccountProfile,
    ) -> AccountProfile:
        """Create or update an account profile.

        Returns:
            AccountProfile: The inserted or updated account profile.

        Raises:
            AccountStoreError: On duplicate account ID with different refs,
                or duplicate ref with different account ID.
        """
        ref_key = (account.provider, str(account.provider_subject))

        # Check for existing by account_id
        existing_by_id = self._accounts_by_id.get(account.account_id)
        if existing_by_id and (
            existing_by_id.provider != account.provider
            or existing_by_id.provider_subject != account.provider_subject
        ):
            msg = "account_id conflict: already exists with different external refs"
            raise AccountStoreError(msg)

        # Check for existing by ref
        existing_by_ref = self._accounts_by_ref.get(ref_key)
        if existing_by_ref and existing_by_ref.account_id != account.account_id:
            msg = "external ref conflict: already exists with different account_id"
            raise AccountStoreError(msg)

        self._insert_account(account)
        return account

    @override
    async def link_account_to_actor(
        self,
        *,
        account_id: AccountId,
        actor_id: ActorId,
    ) -> AccountProfile:
        """Link an account to an internal ActorId.

        Returns:
            AccountProfile: The updated account profile.

        Raises:
            AccountStoreError: If the account_id does not exist.
        """
        account = self._accounts_by_id.get(account_id)
        if not account:
            msg = f"Account not found: {account_id}"
            raise AccountStoreError(msg)

        updated = dataclasses.replace(account, linked_actor_id=actor_id)
        self._insert_account(updated)
        return updated

    @override
    async def unlink_account(
        self,
        account_id: AccountId,
    ) -> AccountProfile:
        """Remove any actor linking from an account.

        Returns:
            AccountProfile: The updated account profile.

        Raises:
            AccountStoreError: If the account_id does not exist.
        """
        account = self._accounts_by_id.get(account_id)
        if not account:
            msg = f"Account not found: {account_id}"
            raise AccountStoreError(msg)

        updated = dataclasses.replace(account, linked_actor_id=None)
        self._insert_account(updated)
        return updated
