"""出力安全性ゲートプロトコルとパススルー実装。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from iris.safety.action_gate import GateDecision, SafetyDecision

if TYPE_CHECKING:
    from iris.contracts.actions import PresentedOutput


class OutputSafetyGate(Protocol):
    """PresentedOutput を検査し、必要ならブロックするゲートのプロトコル。"""

    async def check_output(self, output: PresentedOutput) -> SafetyDecision:
        """PresentedOutput を評価し、安全性判定を返す。"""
        ...


class AllowAllOutputGate:
    """すべての出力を許可するパススルーゲート。"""

    async def check_output(self, output: PresentedOutput) -> SafetyDecision:
        """すべての出力を無条件で許可する。

        Args:
            output: 検査対象の PresentedOutput。

        Returns:
            decision=ALLOW の SafetyDecision。
        """
        _ = self, output
        return SafetyDecision(decision=GateDecision.ALLOW)
