"""プレゼンテーションと安全性を組み立てる、コンストラクタ注入のみの構成。

サービスロケータなし、グローバルレジストリなし、プレゼンテーションロジックなし。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.presentation.event_reaction import EventReactionPresenter
from iris.presentation.presenter import SimplePresenter
from iris.presentation.suite import PresentationSuite
from iris.runtime.output_pipeline import RuntimeOutputPipeline
from iris.safety.action_gate import ActionSafetyGate, AllowAllActionGate
from iris.safety.basic_output_filter import BasicOutputSafetyGate
from iris.safety.output_filter import AllowAllOutputGate, OutputSafetyGate

if TYPE_CHECKING:
    from iris.runtime.config.safety import RuntimeSafetyConfig


def wire_presentation_suite() -> PresentationSuite:
    """PresentationSuite を組み立てる。"""
    return PresentationSuite(
        action_plan_presenter=SimplePresenter(),
        event_reaction_presenter=EventReactionPresenter(),
    )


def wire_action_safety_gate() -> ActionSafetyGate:
    """デフォルトのアクション安全性ゲートを組み立てる。"""
    return AllowAllActionGate()


def wire_output_safety_gate(
    safety_config: RuntimeSafetyConfig | None = None,
) -> OutputSafetyGate:
    """安全性設定に基づいて出力安全性ゲートを組み立てる。"""
    if safety_config is not None and safety_config.mode == "basic":
        return BasicOutputSafetyGate(max_output_chars=safety_config.max_output_chars)
    return AllowAllOutputGate()


def wire_output_pipeline(
    safety_config: RuntimeSafetyConfig | None = None,
) -> RuntimeOutputPipeline:
    """RuntimeOutputPipeline を組み立てる。"""
    return RuntimeOutputPipeline(
        presentation=wire_presentation_suite(),
        action_safety_gate=wire_action_safety_gate(),
        output_safety_gate=wire_output_safety_gate(safety_config=safety_config),
    )
