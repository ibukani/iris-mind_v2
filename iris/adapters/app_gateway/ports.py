from typing import Protocol

from iris.contracts.actions import ActionResult, AppAction
from iris.contracts.observations import Observation


class AppGateway(Protocol):
    async def receive_observation(self) -> Observation | None: ...

    async def execute(self, action: AppAction) -> ActionResult: ...
