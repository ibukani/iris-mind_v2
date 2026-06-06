"""アクション安全性ゲートプロトコルとパススルー実装。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from iris.contracts.actions import ActionPlan


class GateDecision(StrEnum):
    """ゲート判定の取りうる値。"""

    ALLOW = "allow"
    BLOCK = "block"


@dataclass(frozen=True)
class SafetyDecision:
    """安全性ゲート判定の結果。"""

    decision: GateDecision
    reason: str | None = None


class ActionSafetyGate(Protocol):
    """ActionPlan を検査し、必要ならブロックするゲートのプロトコル。"""

    async def check_plan(self, plan: ActionPlan) -> SafetyDecision:
        """ActionPlan を評価し、安全性判定を返す。"""
        ...


class AllowAllActionGate:
    """すべての ActionPlan を許可するパススルーゲート。"""

    async def check_plan(self, plan: ActionPlan) -> SafetyDecision:
        """すべての ActionPlan を無条件で許可する。

        Args:
            plan: 検査対象の ActionPlan。

        Returns:
            decision=ALLOW の SafetyDecision。
        """
        _ = self, plan
        return SafetyDecision(decision=GateDecision.ALLOW)
