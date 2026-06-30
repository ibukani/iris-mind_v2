"""アクション結果後の学習境界で共有する契約。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.actions import ActionResult, AppAction
    from iris.contracts.delivery import DeliveryEnvelope, DeliveryTarget
    from iris.core.ids import ObservationId


@dataclass(frozen=True)
class LearningEvent:
    """受理済み配送結果と学習に必要な配送文脈。"""

    result: ActionResult
    delivery: DeliveryEnvelope | None
    action: AppAction
    target: DeliveryTarget | None
    reported_at: datetime
    source_observation_id: ObservationId | None = None
