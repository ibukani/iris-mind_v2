"""Tests for the presentation and safety wiring constructors."""

from __future__ import annotations

from iris.presentation.presenter import SimplePresenter
from iris.runtime.wiring.presentation import (
    wire_output_pipeline,
    wire_presentation_suite,
    wire_action_safety_gate,
    wire_output_safety_gate,
)
from iris.safety.action_gate import AllowAllActionGate
from iris.safety.output_filter import AllowAllOutputGate


def test_wire_presentation_suite_returns_suite() -> None:
    suite = wire_presentation_suite()
    assert suite is not None
    assert suite.action_plan_presenter is not None
    assert suite.event_reaction_presenter is not None


def test_wire_output_pipeline() -> None:
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
