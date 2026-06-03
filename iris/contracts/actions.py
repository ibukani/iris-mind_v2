from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from iris.core.ids import ActionId, CorrelationId, ExternalRef, SessionId


class ActionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ActionPlan:
    turn_intent: str
    candidate_text: str | None
    should_respond: bool
    priority: int
    interruptible: bool = True

    @property
    def is_no_action(self) -> bool:
        return self.turn_intent == "no_action" and not self.should_respond


@dataclass(frozen=True)
class PresentedOutput:
    text: str | None
    style_hint: str | None = None
    emotion_hint: str | None = None
    expression_hint: str | None = None
    delay_ms: int = 0
    priority: int = 0
    interruptible: bool = True

    @property
    def is_sendable(self) -> bool:
        return self.text is not None


@dataclass(frozen=True)
class AppAction:
    action_id: ActionId
    session_id: SessionId
    correlation_id: CorrelationId


@dataclass(frozen=True)
class SendMessageAction(AppAction):
    text: str


@dataclass(frozen=True)
class NoAction(AppAction):
    reason: str


@dataclass(frozen=True)
class ActionResult:
    action_id: ActionId
    correlation_id: CorrelationId
    status: ActionStatus
    delivered_at: datetime | None = None
    external_message_id: ExternalRef | None = None
    error_reason: str | None = None
