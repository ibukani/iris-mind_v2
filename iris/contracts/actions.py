"""アクション計画、提示、実行の型付き契約。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from iris.core.ids import ActionId, CorrelationId, ExternalRef, SessionId


class ActionStatus(StrEnum):
    """実行されたアクションのステータス。"""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ActionPlan:
    """ターンレベルのアクション決定のための計画。"""

    turn_intent: str
    candidate_text: str | None
    should_respond: bool
    priority: int
    interruptible: bool = True

    @property
    def is_no_action(self) -> bool:
        """この計画が無アクション決定を表す場合にTrue。"""
        return self.turn_intent == "no_action" and not self.should_respond


@dataclass(frozen=True)
class PresentedOutput:
    """セーフティゲートと外部配送の準備ができた出力。"""

    text: str | None
    style_hint: str | None = None
    emotion_hint: str | None = None
    expression_hint: str | None = None
    delay_ms: int = 0
    priority: int = 0
    interruptible: bool = True

    @property
    def is_sendable(self) -> bool:
        """出力が送信可能なテキストを含む場合にTrue。"""
        return self.text is not None


@dataclass(frozen=True)
class AppAction:
    """外部アプリアクションの基本型。"""

    action_id: ActionId
    session_id: SessionId
    correlation_id: CorrelationId


@dataclass(frozen=True)
class SendMessageAction(AppAction):
    """テキストメッセージ送信用のアプリアクション。"""

    text: str


@dataclass(frozen=True)
class NoAction(AppAction):
    """意図的な無操作を表すアプリアクション。"""

    reason: str


@dataclass(frozen=True)
class ActionResult:
    """アプリアクション実行の結果。"""

    action_id: ActionId
    correlation_id: CorrelationId
    status: ActionStatus
    delivered_at: datetime | None = None
    external_message_id: ExternalRef | None = None
    error_reason: str | None = None
