"""AppGateway resolver outputをtyped Observationへ変換するfactory。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.core.ids import ObservationId

if TYPE_CHECKING:
    from iris.adapters.app_gateway.ingress import ActorMessageIngress
    from iris.adapters.app_gateway.ports import IdentityResolver, SpaceResolver

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

    async def create_actor_message(
        self,
        ingress: ActorMessageIngress,
    ) -> ActorMessageObservation:
        """外部provider actor message入力からActorMessageObservationを作る。

        Returns:
            ActorMessageObservation: resolver済みcontextを持つ観測。
        """
        context_metadata = dict(ingress.metadata)
        actor = await self._identity_resolver.resolve_identity(
            ingress.actor,
            device_id=ingress.device_id,
        )
        space_id = None
        if ingress.space is not None:
            space = await self._space_resolver.resolve_space(ingress.space)
            space_id = space.space_id

        return ActorMessageObservation(
            observation_id=self._observation_id_factory(),
            session_id=ingress.session_id,
            context=ObservationContext(
                actor=actor,
                account_id=actor.account_id,
                device_id=actor.device_id,
                space_id=space_id,
                source=ingress.source,
                metadata=context_metadata,
            ),
            occurred_at=ingress.message.occurred_at or self._clock(),
            kind=ObservationKind.ACTOR_MESSAGE,
            text=ingress.message.text,
            external_message_id=ingress.message.external_message_id,
        )
