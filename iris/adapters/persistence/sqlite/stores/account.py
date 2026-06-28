"""SQLite account store implementation using SQLAlchemy."""

from __future__ import annotations

import json
from typing import override

from sqlalchemy import select

from iris.adapters.persistence.sqlite.context import (
    SQLiteDatabaseInput,
    resolve_database_manager,
)
from iris.adapters.persistence.sqlite.schema.account import AccountModel
from iris.contracts.accounts import AccountProfile, AccountStore, AccountStoreError
from iris.core.ids import AccountId, ActorId, ExternalRef


class SQLiteAccountStore(AccountStore):
    """SQLite-backed account store using Async SQLAlchemy."""

    def __init__(self, db: SQLiteDatabaseInput) -> None:
        """Initialize the store and create tables if missing."""
        self._manager = resolve_database_manager(db)

    async def close(self) -> None:
        """Close the database manager.

        This is async but historically sync.
        We will leave it as sync since the framework doesn't await it yet.
        """
        await self._manager.close()

    @staticmethod
    def _model_to_profile(model: AccountModel) -> AccountProfile:
        """Convert an AccountModel to an AccountProfile.

        Returns:
            AccountProfile: The resulting profile.
        """
        return AccountProfile(
            account_id=AccountId(model.account_id),
            provider=model.provider,
            provider_subject=ExternalRef(model.provider_subject),
            display_name=model.display_name,
            linked_actor_id=ActorId(model.linked_actor_id) if model.linked_actor_id else None,
            metadata=model.metadata_dict,
        )

    @override
    async def get_by_external_ref(
        self,
        *,
        provider: str,
        provider_subject: ExternalRef,
    ) -> AccountProfile | None:
        """Get an account profile by provider and subject.

        Returns:
            AccountProfile | None: The found profile or None.
        """
        async with self._manager.transaction() as session:
            stmt = select(AccountModel).where(
                AccountModel.provider == provider,
                AccountModel.provider_subject == str(provider_subject),
            )
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            if not model:
                return None
            return self._model_to_profile(model)

    @override
    async def get_by_account_id(
        self,
        account_id: AccountId,
    ) -> AccountProfile | None:
        """Get an account profile by its internal AccountId.

        Returns:
            AccountProfile | None: The found profile or None.
        """
        async with self._manager.transaction() as session:
            stmt = select(AccountModel).where(AccountModel.account_id == str(account_id))
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            if not model:
                return None
            return self._model_to_profile(model)

    @override
    async def put(
        self,
        account: AccountProfile,
    ) -> AccountProfile:
        """Create or update an account profile.

        Returns:
            AccountProfile: The inserted/updated profile.

        Raises:
            AccountStoreError: If account_id or external ref conflicts exist.
        """
        async with self._manager.transaction() as session:
            # Check for account_id conflict
            stmt_id = select(AccountModel).where(AccountModel.account_id == str(account.account_id))
            result_id = await session.execute(stmt_id)
            existing_by_id = result_id.scalar_one_or_none()
            if existing_by_id and (
                existing_by_id.provider != account.provider
                or existing_by_id.provider_subject != str(account.provider_subject)
            ):
                msg = "account_id conflict: already exists with different external refs"
                raise AccountStoreError(msg)

            # Check for provider/subject conflict
            stmt_ref = select(AccountModel).where(
                AccountModel.provider == account.provider,
                AccountModel.provider_subject == str(account.provider_subject),
            )
            result_ref = await session.execute(stmt_ref)
            existing_by_ref = result_ref.scalar_one_or_none()
            if existing_by_ref and existing_by_ref.account_id != str(account.account_id):
                msg = "external ref conflict: already exists with different account_id"
                raise AccountStoreError(msg)

            if existing_by_id:
                # Update existing
                existing_by_id.display_name = account.display_name
                linked = account.linked_actor_id
                existing_by_id.linked_actor_id = str(linked) if linked else None
                existing_by_id.metadata_json = json.dumps(dict(account.metadata))
            else:
                # Create new
                new_model = AccountModel(
                    account_id=str(account.account_id),
                    provider=account.provider,
                    provider_subject=str(account.provider_subject),
                    display_name=account.display_name,
                    linked_actor_id=(
                        str(account.linked_actor_id) if account.linked_actor_id else None
                    ),
                    metadata_json=json.dumps(dict(account.metadata)),
                )
                session.add(new_model)

        return account
