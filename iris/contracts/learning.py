"""学習境界で共有する契約。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.actions import ActionResult, AppAction, PresentedOutput
    from iris.contracts.delivery import DeliveryEnvelope, DeliveryTarget
    from iris.contracts.observations import Observation
    from iris.core.ids import ObservationId


class RuntimeLearningEventKind(StrEnum):
    """runtime内で確定したpost-result学習イベントの種類。"""

    INLINE_RESPONSE_GENERATED = "inline_response_generated"
    NO_ACTION = "no_action"
    USER_FEEDBACK = "user_feedback"


@dataclass(frozen=True)
class RuntimeLearningEvent:
    """配送結果を伴わないruntime outcome学習イベント。"""

    kind: RuntimeLearningEventKind
    observation: Observation
    output: PresentedOutput | None
    occurred_at: datetime
    route: str
    source_observation_id: ObservationId


@dataclass(frozen=True)
class LearningEvent:
    """受理済み配送結果と学習に必要な配送文脈。"""

    result: ActionResult
    delivery: DeliveryEnvelope | None
    action: AppAction
    target: DeliveryTarget | None
    reported_at: datetime
    source_observation_id: ObservationId | None = None
