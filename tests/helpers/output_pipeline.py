"""Tests向けの型付きoutput pipeline構成helper。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.presentation.event_reaction import EventReactionPresenter
from iris.presentation.presenter import SimplePresenter
from iris.presentation.suite import PresentationSuite
from iris.runtime.output_pipeline import RuntimeOutputPipeline
from iris.safety.action_gate import AllowAllActionGate
from iris.safety.output_filter import AllowAllOutputGate

if TYPE_CHECKING:
    from iris.presentation.ports import ActionPlanPresenter
    from iris.safety.action_gate import ActionSafetyGate
    from iris.safety.output_filter import OutputSafetyGate


def make_output_pipeline(
    *,
    presenter: ActionPlanPresenter | None = None,
    action_gate: ActionSafetyGate | None = None,
    output_gate: OutputSafetyGate | None = None,
) -> RuntimeOutputPipeline:
    """指定したtest doubleでoutput pipelineを構築する。

    Returns:
        構成済みpipeline。
    """
    return RuntimeOutputPipeline(
        presentation=PresentationSuite(
            presenters=(presenter or SimplePresenter(), EventReactionPresenter()),
        ),
        action_safety_gate=action_gate or AllowAllActionGate(),
        output_safety_gate=output_gate or AllowAllOutputGate(),
    )
