"""Tests for the presentation and safety wiring constructors."""

from __future__ import annotations

from iris.presentation.action_plan import DefaultActionPlanPresenter
from iris.runtime.wiring.presentation import (
    wire_action_safety_gate,
    wire_output_pipeline,
    wire_output_safety_gate,
    wire_presentation_suite,
)
from iris.safety.action_gate import AllowAllActionGate
from iris.safety.output_filter import AllowAllOutputGate


def test_wire_presentation_suite_returns_suite() -> None:
    """標準presenter群をsuiteとして構成する。"""
    suite = wire_presentation_suite([DefaultActionPlanPresenter()])
    assert suite is not None
    assert len(suite.presenters) >= 1


def test_wire_output_pipeline() -> None:
    """Presentationとsafety gateを単一pipelineへ構成する。"""
    pipeline = wire_output_pipeline()
    assert pipeline is not None
    assert pipeline.action_safety_gate is not None
    assert pipeline.output_safety_gate is not None


def test_wire_action_safety_gate_returns_allow_all() -> None:
    """wire_action_safety_gate returns the default allow-all gate."""
    gate = wire_action_safety_gate()
    assert isinstance(gate, AllowAllActionGate)


def test_wire_output_safety_gate_returns_allow_all() -> None:
    """wire_output_safety_gate returns the default allow-all gate."""
    gate = wire_output_safety_gate()
    assert isinstance(gate, AllowAllOutputGate)


def test_wire_presentation_suite_keeps_extension_presenters_before_default() -> None:
    """feature-specific presenter が default presenter より優先されることを固定する。"""

    class ExtensionPresenter(DefaultActionPlanPresenter):
        pass

    extension = ExtensionPresenter()
    suite = wire_presentation_suite([extension])

    assert suite.presenters[0] is extension
    assert isinstance(suite.presenters[-1], DefaultActionPlanPresenter)
