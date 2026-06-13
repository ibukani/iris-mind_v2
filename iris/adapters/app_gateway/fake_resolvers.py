"""決定論的なAppGateway identity/space resolver実装。"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.adapters.accounts.memory import InMemoryAccountStore
from iris.adapters.app_gateway.ports import AccountStore, IdentityResolver, SpaceResolver
from iris.adapters.app_gateway.stable_ids import stable_account_id, stable_actor_id, stable_space_id
from iris.contracts.accounts import AccountProfile
from iris.contracts.identity import Identity
from iris.contracts.spaces import InteractionSpace

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.contracts.external_refs import ExternalAccountRef, ExternalSpaceRef
    from iris.core.ids import ActorId, DeviceId


class FakeIdentityResolver(IdentityResolver):
    """テストとローカル配線向けの決定論的IdentityResolver。"""

    def __init__(
        self,
        *,
        account_store: AccountStore | None = None,
        linked_actor_ids: Mapping[tuple[str, str], ActorId] | None = None,
    ) -> None:
        """テスト用のリンクリストを使ってresolverを初期化する。"""
        self._linked_actor_ids = dict(linked_actor_ids or {})
        self._account_store = account_store or InMemoryAccountStore()

    @override
    async def resolve_identity(
        self,
        account_ref: ExternalAccountRef,
        *,
        device_id: DeviceId | None = None,
    ) -> Identity:
        """AccountProfile/AccountStoreを使ってIdentityを解決する。

        Returns:
            Identity: 外部refから決定論的に解決されたIdentity。
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

        # Check explicit links from constructor mapping
        link_key = (account_ref.provider, str(account_ref.provider_subject))
        link_target = self._linked_actor_ids.get(link_key)
        if link_target and profile.linked_actor_id != link_target:
            profile = await self._account_store.link_account_to_actor(
                account_id=profile.account_id,
                actor_id=link_target,
            )

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


class FakeSpaceResolver(SpaceResolver):
    """テストとローカル配線向けの決定論的SpaceResolver。"""

    @override
    async def resolve_space(
        self,
        space_ref: ExternalSpaceRef,
    ) -> InteractionSpace:
        """同じprovider/provider_space_refから同じSpaceIdを持つInteractionSpaceを返す。

        Returns:
            InteractionSpace: 外部refから決定論的に解決されたInteractionSpace。
        """
        space_id = stable_space_id(space_ref.provider, space_ref.provider_space_ref)
        return InteractionSpace(
            space_id=space_id,
            space_kind=space_ref.space_kind,
            display_name=space_ref.display_name,
            metadata=dict(space_ref.metadata),
        )
