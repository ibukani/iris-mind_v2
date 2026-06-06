"""テストとローカル配線向けの決定論的FakeAppGateway。"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from typing import TYPE_CHECKING, override

from iris.adapters.app_gateway.fake_resolvers import FakeIdentityResolver, FakeSpaceResolver
from iris.adapters.app_gateway.observation_factory import (
    Clock,
    ObservationFactory,
    SequentialObservationIdFactory,
)
from iris.adapters.app_gateway.ports import AppGateway
from iris.contracts.actions import ActionResult, ActionStatus, AppAction

if TYPE_CHECKING:
    from iris.adapters.app_gateway.ingress import ActorMessageIngress
    from iris.contracts.observations import ActorMessageObservation, Observation


class FakeAppGateway(AppGateway):
    """ObservationFactoryで観測を作りFIFOで返すFake AppGateway。"""

    def __init__(
        self,
        *,
        observation_factory: ObservationFactory | None = None,
        clock: Clock | None = None,
    ) -> None:
        """Fake gatewayをper-instance queueと決定論的依存で初期化する。"""
        self._clock = clock or _fixed_clock
        self._observation_factory = observation_factory or ObservationFactory(
            identity_resolver=FakeIdentityResolver(),
            space_resolver=FakeSpaceResolver(),
            observation_id_factory=SequentialObservationIdFactory(prefix="fake-obs"),
            clock=self._clock,
        )
        self._queue: deque[Observation] = deque()

    async def ingest_actor_message(
        self,
        ingress: ActorMessageIngress,
    ) -> ActorMessageObservation:
        """Actor message観測を作ってFIFO queueへ追加する。

        Returns:
            ActorMessageObservation: queueへ追加した観測。
        """
        observation = await self._observation_factory.create_actor_message(ingress)
        self._queue.append(observation)
        return observation

    @override
    async def receive_observation(self) -> Observation | None:
        """FIFO queueから次の観測を返す。

        Returns:
            Observation | None: queueが空ならNone。
        """
        if not self._queue:
            return None
        return self._queue.popleft()

    @override
    async def execute(self, action: AppAction) -> ActionResult:
        """AppActionを成功扱いにした決定論的ActionResultを返す。

        Returns:
            ActionResult: action ID/correlation IDを保持する成功結果。
        """
        return ActionResult(
            action_id=action.action_id,
            correlation_id=action.correlation_id,
            status=ActionStatus.SUCCEEDED,
            delivered_at=self._clock(),
        )


def _fixed_clock() -> datetime:
    """Fake gateway defaultの固定UTC時刻を返す。

    Returns:
        datetime: 固定timezone-aware UTC datetime。
    """
    return datetime(2026, 6, 5, tzinfo=UTC)
