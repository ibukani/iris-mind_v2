"""Runtime wiring helper tests for context assembly."""

from __future__ import annotations

from iris.runtime.state.availability import AvailabilityResolver
from iris.runtime.state.context_assembler import WorkspaceContextAssembler
from iris.runtime.wiring.availability import wire_availability_resolver
from iris.runtime.wiring.context import wire_workspace_context_assembler


def test_wire_availability_resolver_returns_default_resolver() -> None:
    """wire_availability_resolver はデフォルトの resolver を返す。"""
    resolver = wire_availability_resolver()
    assert isinstance(resolver, AvailabilityResolver)
    expected_window = 300.0
    assert resolver.recent_activity_window_seconds == expected_window


def test_wire_availability_resolver_uses_custom_window() -> None:
    """wire_availability_resolver は window 秒数を反映する。"""
    resolver = wire_availability_resolver(recent_activity_window_seconds=60.0)
    expected_window = 60.0
    assert resolver.recent_activity_window_seconds == expected_window


def test_wire_workspace_context_assembler_defaults() -> None:
    """wire_workspace_context_assembler は省略時にデフォルト resolver / now を使う。"""
    assembler = wire_workspace_context_assembler()

    assert isinstance(assembler, WorkspaceContextAssembler)
    assert isinstance(assembler.availability_resolver, AvailabilityResolver)
    assert assembler.activity_projection_store is None
    assert assembler.presence_store is None
    assert assembler.occupancy_store is None
