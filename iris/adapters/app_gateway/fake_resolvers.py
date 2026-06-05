"""決定論的なAppGateway identity/space resolver実装。"""

from __future__ import annotations

from hashlib import blake2b
from typing import TYPE_CHECKING, override

from iris.adapters.app_gateway.ports import IdentityResolver, SpaceResolver
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


class FakeIdentityResolver(IdentityResolver):
    """テストとローカル配線向けの決定論的IdentityResolver。"""

    def __init__(
        self,
        *,
        linked_actor_ids: Mapping[tuple[str, str], ActorId] | None = None,
    ) -> None:
        """テスト用のリンクリストを使ってresolverを初期化する。"""
        self._linked_actor_ids = dict(linked_actor_ids or {})

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
        """同じprovider/provider_subjectから同じActorIdを持つIdentityを返す。

        Returns:
            Identity: 外部refから決定論的に解決されたIdentity。
        """
        # Determine account_id
        resolved_account_id = AccountId(account_id or f"account-{provider}-{provider_subject}")

        # Determine actor_id from configured links or fallback to account-based stable ID
        actor_id = self._linked_actor_ids.get((provider, str(provider_subject)))
        if not actor_id:
            actor_id = ActorId(_stable_id("actor", "", str(resolved_account_id)))

        return Identity(
            actor_id=actor_id,
            actor_kind=actor_kind,
            display_name=display_name,
            provider=provider,
            provider_subject=provider_subject,
            account_id=resolved_account_id,
            device_id=device_id,
            metadata=dict(metadata or {}),
        )


class FakeSpaceResolver(SpaceResolver):
    """テストとローカル配線向けの決定論的SpaceResolver。"""

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
        """同じprovider/provider_space_refから同じSpaceIdを持つInteractionSpaceを返す。

        Returns:
            InteractionSpace: 外部refから決定論的に解決されたInteractionSpace。
        """
        return InteractionSpace(
            space_id=SpaceId(_stable_id("space", provider, str(provider_space_ref))),
            space_kind=space_kind,
            display_name=display_name,
            participants=tuple(_space_participant(identity) for identity in participants),
            metadata=dict(metadata or {}),
        )


def _stable_id(prefix: str, provider: str, external_ref: str) -> str:
    """Resolver用の短い決定論的ID文字列を作る。

    Returns:
        str: prefix付きの決定論的ID。
    """
    digest = blake2b(
        f"{provider}:{external_ref}".encode(),
        digest_size=12,
    ).hexdigest()
    return f"{prefix}-{provider}-{digest}"


def _space_participant(identity: Identity) -> SpaceParticipant:
    """IdentityからSpaceParticipant snapshotを作る。

    Returns:
        SpaceParticipant: Identityを含む参加者snapshot。
    """
    return SpaceParticipant(
        actor_id=identity.actor_id,
        participant_kind=SpaceParticipantKind(identity.actor_kind.value),
        display_name=identity.display_name,
        identity=identity,
    )
