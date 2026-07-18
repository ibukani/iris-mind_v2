"""アクション計画、提示、実行の型付き契約。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from iris.contracts.presentation_hints import PresentationHints
from iris.contracts.safety import SafetyContext
from iris.core.ids import ActionId, CorrelationId, ExternalRef, SessionId


class ActionStatus(StrEnum):
    """実行されたアクションのステータス。"""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


_ERR_INVALID_NO_ACTION = "no_action plan must not include candidate text or response intent"
_ERR_SENDABLE_OUTPUT_REQUIRED = "sendable PresentedOutput required"


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
    presentation_hints: PresentationHints = Field(default_factory=PresentationHints)
    safety_block_reason: str | None = None
    policy_constraint_names: tuple[str, ...] = ()
    safety_contexts: tuple[SafetyContext, ...] = ()

    @property
    def style_hint(self) -> str | None:
        """旧flat style hintの読み取り経路を返す。"""
        return self.presentation_hints.style_hint

    @property
    def emotion_hint(self) -> str | None:
        """旧flat emotion hintの読み取り経路を返す。"""
        return self.presentation_hints.emotion_hint

    @property
    def expression_hint(self) -> str | None:
        """旧flat expression hintの読み取り経路を返す。"""
        return self.presentation_hints.expression_hint

    @property
    def delay_ms(self) -> int:
        """旧flat delayの読み取り経路を返す。"""
        return self.presentation_hints.delay_ms

    @property
    def priority(self) -> int:
        """旧flat priorityの読み取り経路を返す。"""
        return self.presentation_hints.priority

    @property
    def interruptible(self) -> bool:
        """旧flat interruptibleの読み取り経路を返す。"""
        return self.presentation_hints.interruptible

    @property
    def is_sendable(self) -> bool:
        """出力が送信可能なテキストを含む場合にTrue。"""
        return self.text is not None and bool(self.text.strip())


def presented_output_from_plan(
    plan: ActionPlan,
    *,
    style_hint: str | None = None,
) -> PresentedOutput:
    """ActionPlan の共通フィールドを PresentedOutput へ写像する。

    Args:
        plan: 変換元のアクションプラン。
        style_hint: 必要に応じて付与する表示ヒント。

    Returns:
        変換済みの提示出力。no_action の場合は非送信出力。
    """
    if plan.is_no_action:
        return PresentedOutput(text=None)
    return PresentedOutput(
        text=plan.candidate_text,
        presentation_hints=PresentationHints(
            style_hint=style_hint,
            priority=plan.priority,
            interruptible=plan.interruptible,
            delay_ms=plan.delay_ms,
        ),
    )


def presented_output_with_policy_constraints(
    output: PresentedOutput,
    constraint_names: tuple[str, ...],
) -> PresentedOutput:
    """PresentedOutput に policy provenance を型安全に付与する。

    Returns:
        元の表示属性とpolicy constraint名を持つ出力。
    """
    return presented_output_with_policy_metadata(
        output,
        constraint_names=constraint_names,
        safety_contexts=(),
    )


def presented_output_with_policy_metadata(
    output: PresentedOutput,
    *,
    constraint_names: tuple[str, ...],
    safety_contexts: tuple[SafetyContext, ...],
) -> PresentedOutput:
    """PresentedOutput に policy constraint と safety context metadata を付与する。

    Returns:
        元の表示属性とpolicy metadataを持つ出力。
    """
    return PresentedOutput(
        text=output.text,
        presentation_hints=output.presentation_hints,
        safety_block_reason=output.safety_block_reason,
        policy_constraint_names=_merge_constraint_names(
            output.policy_constraint_names,
            constraint_names,
        ),
        safety_contexts=_merge_safety_contexts(
            output.safety_contexts,
            safety_contexts,
        ),
    )


def _merge_safety_contexts(
    existing: tuple[SafetyContext, ...],
    additional: tuple[SafetyContext, ...],
) -> tuple[SafetyContext, ...]:
    merged: list[SafetyContext] = []
    for context in (*existing, *additional):
        if context not in merged:
            merged.append(context)
    return tuple(merged)


def _merge_constraint_names(
    existing: tuple[str, ...],
    additional: tuple[str, ...],
) -> tuple[str, ...]:
    merged: list[str] = []
    for name in (*existing, *additional):
        if name not in merged:
            merged.append(name)
    return tuple(merged)


class AppAction(BaseModel):
    """外部アプリアクションの基本型。"""

    model_config = ConfigDict(frozen=True)

    action_id: ActionId
    session_id: SessionId
    correlation_id: CorrelationId


class SendMessageAction(AppAction):
    """テキストメッセージ送信用のアプリアクション。"""

    text: str
    presentation_hints: PresentationHints = Field(default_factory=PresentationHints)


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


def send_message_action_from_output(
    output: PresentedOutput,
    *,
    action_id: ActionId,
    session_id: SessionId,
    correlation_id: CorrelationId,
) -> SendMessageAction:
    """正本の提示ヒントを保持した配送actionを作る。

    Returns:
        出力textと提示ヒントを含む配送action。

    Raises:
        ValueError: outputが送信可能でない場合。
    """
    if not output.is_sendable or output.safety_block_reason is not None:
        raise ValueError(_ERR_SENDABLE_OUTPUT_REQUIRED)
    return SendMessageAction(
        action_id=action_id,
        session_id=session_id,
        correlation_id=correlation_id,
        text=output.text or "",
        presentation_hints=output.presentation_hints,
    )
