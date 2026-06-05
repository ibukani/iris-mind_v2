"""外部アプリゲートウェイアダプタ境界のポート定義。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from iris.contracts.identity import ActorKind

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from iris.contracts.actions import ActionResult, AppAction
    from iris.contracts.identity import Identity
    from iris.contracts.observations import Observation
    from iris.contracts.spaces import InteractionSpace, SpaceKind
    from iris.core.ids import AccountId, DeviceId, ExternalRef


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

    async def resolve_actor(  # noqa: PLR0913 -- resolver port mirrors typed external context fields
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
        """外部provider subjectから型付きIdentityを返す。"""
        ...


class SpaceResolver(Protocol):
    """外部provider space refをIris InteractionSpaceへ解決するAppGateway境界port。"""

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
        """外部provider space refから型付きInteractionSpaceを返す。"""
        ...
