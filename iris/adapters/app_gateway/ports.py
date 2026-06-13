"""外部アプリゲートウェイアダプタ境界のポート定義。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from iris.contracts.accounts import AccountProfile
    from iris.contracts.actions import ActionResult, AppAction
    from iris.contracts.external_refs import ExternalAccountRef, ExternalSpaceRef
    from iris.contracts.identity import Identity
    from iris.contracts.observations import Observation
    from iris.contracts.spaces import InteractionSpace, SpaceBinding
    from iris.core.ids import AccountId, ActorId, DeviceId, ExternalRef


class AppGateway(Protocol):
    """観測の受信とアプリアクション実行のためのプロトコル。"""

    async def receive_observation(self) -> Observation | None:
        """外部アプリから次の観測を受信する。イベントがない場合はNoneを返す。"""
        ...

    async def execute(self, action: AppAction) -> ActionResult:
        """アプリアクションを実行し、結果を返す。"""
        ...


class IdentityResolver(Protocol):
    """外部provider subjectをIris Identityへ解決するAppGateway境界port。"""

    async def resolve_identity(
        self,
        account_ref: ExternalAccountRef,
        *,
        device_id: DeviceId | None = None,
    ) -> Identity:
        """Resolve an external provider account into an Iris Identity.

        The implementation may create or look up AccountProfile and link it to an Actor.
        """
        ...


class SpaceResolver(Protocol):
    """外部provider space refをIris InteractionSpaceへ解決するAppGateway境界port。"""

    async def resolve_space(
        self,
        space_ref: ExternalSpaceRef,
    ) -> InteractionSpace:
        """外部provider space refから型付きInteractionSpaceを返す。"""
        ...


class SpaceBindingStore(Protocol):
    """Reserved extension protocol for external space binding storage.

    The default Iris-Mind runtime does not persist or wire SpaceBinding.
    Default space resolution is ephemeral and deterministic from
    provider + provider_space_ref.
    """

    async def get_by_external_ref(
        self,
        *,
        provider: str,
        provider_space_ref: ExternalRef,
    ) -> SpaceBinding | None:
        """Get a space binding by provider and external space ref."""
        ...

    async def put(
        self,
        binding: SpaceBinding,
    ) -> SpaceBinding:
        """Create or replace a space binding."""
        ...


class AccountStore(Protocol):
    """External account profile storage and linking protocol."""

    async def get_by_external_ref(
        self,
        *,
        provider: str,
        provider_subject: ExternalRef,
    ) -> AccountProfile | None:
        """Get an account profile by provider and subject."""
        ...

    async def get_by_account_id(
        self,
        account_id: AccountId,
    ) -> AccountProfile | None:
        """Get an account profile by its internal AccountId."""
        ...

    async def put(
        self,
        account: AccountProfile,
    ) -> AccountProfile:
        """Create or update an account profile."""
        ...

    async def link_account_to_actor(
        self,
        *,
        account_id: AccountId,
        actor_id: ActorId,
    ) -> AccountProfile:
        """Link an account to an internal ActorId."""
        ...

    async def unlink_account(
        self,
        account_id: AccountId,
    ) -> AccountProfile:
        """Remove any actor linking from an account."""
        ...
