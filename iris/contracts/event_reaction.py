"""イベント反応（event reaction）の決定と内容を表す契約。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from iris.contracts.actions import ActionPlan


class EventReactionDecision(BaseModel):
    """イベント反応を行うかどうかの決定。"""

    model_config = ConfigDict(frozen=True)

    should_react: bool
    reason: str
    candidate: ActionPlan | None = None
