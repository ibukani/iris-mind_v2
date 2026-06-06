"""プレゼンテーションと安全性を組み立てる、コンストラクタ注入のみの構成。

サービスロケータなし、グローバルレジストリなし、プレゼンテーションロジックなし。
"""

from __future__ import annotations

from iris.presentation.presenter import Presenter, SimplePresenter
from iris.safety.action_gate import ActionSafetyGate, AllowAllActionGate
from iris.safety.output_filter import AllowAllOutputGate, OutputSafetyGate


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


def wire_output_safety_gate() -> OutputSafetyGate:
    """デフォルトの出力安全性ゲートを組み立てる。

    Returns:
        AllowAllOutputGate インスタンス。
    """
    return AllowAllOutputGate()
