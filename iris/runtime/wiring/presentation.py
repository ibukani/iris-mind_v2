"""Constructor-injection-only composition for presentation and safety.

No service locator, no global registry, no presentation logic.
"""

from __future__ import annotations

from iris.presentation.presenter import Presenter, SimplePresenter
from iris.safety.action_gate import ActionSafetyGate, AllowAllActionGate
from iris.safety.output_filter import AllowAllOutputGate, OutputSafetyGate


def wire_presenter() -> Presenter:
    """Wire the default presenter.

    Returns:
        A SimplePresenter instance.
    """
    return SimplePresenter()


def wire_action_safety_gate() -> ActionSafetyGate:
    """Wire the default action safety gate.

    Returns:
        An AllowAllActionGate instance.
    """
    return AllowAllActionGate()


def wire_output_safety_gate() -> OutputSafetyGate:
    """Wire the default output safety gate.

    Returns:
        An AllowAllOutputGate instance.
    """
    return AllowAllOutputGate()
