"""アクション計画、提示、実行の型付き契約。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

from iris.core.ids import ActionId, CorrelationId, ExternalRef, SessionId


class ActionStatus(StrEnum):
    """実行されたアクションのステータス。"""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


_ERR_INVALID_NO_ACTION = "no_action plan must not include candidate text or response intent"


class ActionPlan(BaseModel):
    """ターンレベルのアクション決定のための計画。"""

    model_config = ConfigDict(frozen=True)

    turn_intent: str
    candidate_text: str | None
    should_respond: bool
    priority: int
    interruptible: bool = True
    delay_ms: int = 0

    @classmethod
    def no_action(cls) -> ActionPlan:
        """何もアクションを行わないプランを生成して返す。

        Returns:
            ActionPlan: turn_intent="no_action" の ActionPlan。
        """
        return cls(
            turn_intent="no_action",
            candidate_text=None,
            should_respond=False,
            priority=-1,
        )

    @model_validator(mode="after")
    def _validate_no_action(self) -> ActionPlan:
        """no_actionプランの不変条件を検証する。

        Returns:
            検証済みplan。

        Raises:
            ValueError: no-action不変条件に違反した場合。
        """
        if self.turn_intent == "no_action" and (
            self.candidate_text is not None or self.should_respond
        ):
            raise ValueError(_ERR_INVALID_NO_ACTION)
        return self

    @property
    def is_no_action(self) -> bool:
        """この計画が無アクション決定を表す場合にTrue。"""
        return (
            self.turn_intent == "no_action"
            and self.candidate_text is None
            and not self.should_respond
        )


class PresentedOutput(BaseModel):
    """セーフティゲートと外部配送の準備ができた出力。"""

    model_config = ConfigDict(frozen=True)

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
        return self.text is not None and bool(self.text.strip())


class AppAction(BaseModel):
    """外部アプリアクションの基本型。"""

    model_config = ConfigDict(frozen=True)

    action_id: ActionId
    session_id: SessionId
    correlation_id: CorrelationId


class SendMessageAction(AppAction):
    """テキストメッセージ送信用のアプリアクション。"""

    text: str


class NoAction(AppAction):
    """意図的な無操作を表すアプリアクション。"""

    reason: str


class ActionResult(BaseModel):
    """アプリアクション実行の結果。"""

    model_config = ConfigDict(frozen=True)

    action_id: ActionId
    correlation_id: CorrelationId
    status: ActionStatus
    delivered_at: datetime | None = None
    external_message_id: ExternalRef | None = None
    error_reason: str | None = None
