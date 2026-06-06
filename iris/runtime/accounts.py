"""ランタイム AccountService。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.adapters.app_gateway.ports import AccountStore
    from iris.contracts.accounts import AccountProfile
    from iris.core.ids import AccountId, ActorId, ExternalRef


class AccountService:
    """明示的なアカウント参照・連携のための内部ランタイムサービス。"""

    def __init__(self, account_store: AccountStore) -> None:
        """アカウントストアでサービスを初期化する。"""
        self._account_store = account_store

    async def get_account_by_id(
        self,
        account_id: AccountId,
    ) -> AccountProfile | None:
        """内部 AccountId でアカウントプロフィールを取得する。

        Returns:
            AccountProfile | None: 見つかったアカウントプロフィール。なければ None。
        """
        return await self._account_store.get_by_account_id(account_id)

    async def get_account_by_external_ref(
        self,
        *,
        provider: str,
        provider_subject: ExternalRef,
    ) -> AccountProfile | None:
        """プロバイダーとサブジェクトでアカウントプロフィールを取得する。

        Returns:
            AccountProfile | None: 見つかったアカウントプロフィール。なければ None。
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
        """アカウントを内部 ActorId に紐づける。

        Returns:
            AccountProfile: 更新されたアカウントプロフィール。
        """
        return await self._account_store.link_account_to_actor(
            account_id=account_id,
            actor_id=actor_id,
        )

    async def unlink_account(
        self,
        account_id: AccountId,
    ) -> AccountProfile:
        """アカウントからアクター連携を除去する。

        Returns:
            AccountProfile: 更新されたアカウントプロフィール。
        """
        return await self._account_store.unlink_account(account_id)
