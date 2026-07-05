"""basic_action diagnostic echo feature のテスト。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.cognitive.workspace.frame import InterpretedInput, WorkspaceFrame
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import ObservationId, SessionId
from iris.features.basic_action.definition import (
    DiagnosticEchoActionSelectionStep,
    define_basic_action_feature,
)
from iris.features.definition import FeatureKind


def _frame_with_text(text: str | None) -> WorkspaceFrame:
    return WorkspaceFrame(
        observation=ActorMessageObservation(
            observation_id=ObservationId("obs-diagnostic-echo"),
            session_id=SessionId("session-diagnostic-echo"),
            context=ObservationContext(),
            occurred_at=datetime.now(UTC),
            kind=ObservationKind.ACTOR_MESSAGE,
            text=text or "",
        ),
        interpreted_input=InterpretedInput(text=text),
    )


@pytest.mark.anyio
async def test_diagnostic_echo_action_selection_returns_input_text() -> None:
    """Diagnostic echo step は入力 text をそのまま候補 plan にする。"""
    result = await DiagnosticEchoActionSelectionStep().run(_frame_with_text("hello"))

    assert result.action_plans[0].candidate_text == "hello"
    assert result.action_plans[0].should_respond is True


@pytest.mark.anyio
async def test_diagnostic_echo_action_selection_no_sends_without_text() -> None:
    """入力 text がない場合は no-send 候補になる。"""
    result = await DiagnosticEchoActionSelectionStep().run(_frame_with_text(None))

    assert result.action_plans[0].candidate_text is None
    assert result.action_plans[0].should_respond is False


def test_basic_action_feature_is_diagnostic_and_has_no_presenter() -> None:
    """basic_action は diagnostic feature で、汎用 presenter を所有しない。"""
    feature = define_basic_action_feature()

    assert feature.name == "basic_action"
    assert feature.kind is FeatureKind.DIAGNOSTIC
    assert feature.action_plan_presenters == ()
    assert len(feature.cognitive_steps) == 1
