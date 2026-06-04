"""Tests for the presentation and safety wiring constructors."""

from __future__ import annotations

from iris.presentation.presenter import SimplePresenter
from iris.runtime.wiring.presentation import (
    wire_action_safety_gate,
    wire_output_safety_gate,
    wire_presenter,
)
from iris.safety.action_gate import AllowAllActionGate
from iris.safety.output_filter import AllowAllOutputGate


def test_wire_presenter_returns_simple_presenter() -> None:
    """wire_presenter returns a SimplePresenter instance."""
    presenter = wire_presenter()
    assert isinstance(presenter, SimplePresenter)


def test_wire_action_safety_gate_returns_allow_all() -> None:
    """wire_action_safety_gate returns the default allow-all gate."""
    gate = wire_action_safety_gate()
    assert isinstance(gate, AllowAllActionGate)


def test_wire_output_safety_gate_returns_allow_all() -> None:
    """wire_output_safety_gate returns the default allow-all gate."""
    gate = wire_output_safety_gate()
    assert isinstance(gate, AllowAllOutputGate)
