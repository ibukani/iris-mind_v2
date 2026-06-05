"""AppGateway resolver outputをtyped Observationへ変換するfactory。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from iris.contracts.identity import ActorKind
from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.contracts.spaces import SpaceKind
from iris.core.ids import ObservationId

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.adapters.app_gateway.ports import IdentityResolver, SpaceResolver
    from iris.core.ids import AccountId, DeviceId, ExternalRef, SessionId

Clock = Callable[[], datetime]
ObservationIdFactory = Callable[[], ObservationId]


@dataclass
class SequentialObservationIdFactory:
    """テスト可能なper-instance連番ObservationId factory。"""

    prefix: str = "obs"
    next_value: int = 1

    def __call__(self) -> ObservationId:
        """次のObservationIdを返す。

        Returns:
            ObservationId: prefix付き連番ID。
        """
        observation_id = ObservationId(f"{self.prefix}-{self.next_value}")
        self.next_value += 1
        return observation_id


class ObservationFactory:
    """Identity/Space resolverを使ってActorMessageObservationを作るfactory。"""

    def __init__(
        self,
        *,
        identity_resolver: IdentityResolver,
        space_resolver: SpaceResolver,
        observation_id_factory: ObservationIdFactory,
        clock: Clock,
    ) -> None:
        """依存resolver、ID factory、clockを注入する。"""
        self._identity_resolver = identity_resolver
        self._space_resolver = space_resolver
        self._observation_id_factory = observation_id_factory
        self._clock = clock

    async def create_actor_message(  # noqa: PLR0913 -- typed app gateway event fields stay explicit
        self,
        *,
        provider: str,
        provider_subject: ExternalRef,
        display_name: str,
        text: str,
        session_id: SessionId,
        provider_space_ref: ExternalRef | None = None,
        space_display_name: str | None = None,
        space_kind: SpaceKind = SpaceKind.CHANNEL,
        account_id: AccountId | None = None,
        device_id: DeviceId | None = None,
        actor_kind: ActorKind = ActorKind.HUMAN,
        source: str | None = None,
        occurred_at: datetime | None = None,
        external_message_id: ExternalRef | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> ActorMessageObservation:
        """外部provider actor message入力からActorMessageObservationを作る。

        Returns:
            ActorMessageObservation: resolver済みcontextを持つ観測。
        """
        context_metadata = dict(metadata or {})
        actor = await self._identity_resolver.resolve_identity(
            provider=provider,
            provider_subject=provider_subject,
            display_name=display_name,
            actor_kind=actor_kind,
            account_id=account_id,
            device_id=device_id,
            metadata=context_metadata,
        )
        space_id = None
        if provider_space_ref is not None:
            space = await self._space_resolver.resolve_space(
                provider=provider,
                provider_space_ref=provider_space_ref,
                display_name=space_display_name or str(provider_space_ref),
                space_kind=space_kind,
                participants=(actor,),
                metadata=context_metadata,
            )
            space_id = space.space_id

        return ActorMessageObservation(
            observation_id=self._observation_id_factory(),
            session_id=session_id,
            context=ObservationContext(
                actor=actor,
                account_id=actor.account_id,
                device_id=actor.device_id,
                space_id=space_id,
                source=source,
                metadata=context_metadata,
            ),
            occurred_at=occurred_at or self._clock(),
            kind=ObservationKind.ACTOR_MESSAGE,
            text=text,
            external_message_id=external_message_id,
        )
