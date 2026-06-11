"""プレゼンテーションと安全性を組み立てる、コンストラクタ注入のみの構成。

サービスロケータなし、グローバルレジストリなし、プレゼンテーションロジックなし。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.presentation.presenter import Presenter, SimplePresenter
from iris.safety.action_gate import ActionSafetyGate, AllowAllActionGate
from iris.safety.basic_output_filter import BasicOutputSafetyGate
from iris.safety.output_filter import AllowAllOutputGate, OutputSafetyGate

if TYPE_CHECKING:
    from iris.runtime.config.safety import RuntimeSafetyConfig


def wire_presenter() -> Presenter:
    """デフォルトの Presenter を組み立てる。

    Returns:
        SimplePresenter インスタンス。
    """
    return SimplePresenter()


def wire_action_safety_gate() -> ActionSafetyGate:
    """デフォルトのアクション安全性ゲートを組み立てる。

    Returns:
        AllowAllActionGate インスタンス。
    """
    return AllowAllActionGate()


def wire_output_safety_gate(
    safety_config: RuntimeSafetyConfig | None = None,
) -> OutputSafetyGate:
    """安全性設定に基づいて出力安全性ゲートを組み立てる。

    Args:
        safety_config: 安全性設定。省略時は AllowAllOutputGate。

    Returns:
        OutputSafetyGate インスタンス。
    """
    if safety_config is not None and safety_config.mode == "basic":
        return BasicOutputSafetyGate(max_output_chars=safety_config.max_output_chars)
    return AllowAllOutputGate()
