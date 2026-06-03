"""Constructor-injection-only composition for presentation and safety.

No service locator, no global registry, no presentation logic.
"""

from iris.presentation.presenter import Presenter, SimplePresenter
from iris.safety.action_gate import ActionSafetyGate, AllowAllActionGate
from iris.safety.output_filter import AllowAllOutputGate, OutputSafetyGate


def wire_presenter() -> Presenter:
    return SimplePresenter()


def wire_action_safety_gate() -> ActionSafetyGate:
    return AllowAllActionGate()


def wire_output_safety_gate() -> OutputSafetyGate:
    return AllowAllOutputGate()
