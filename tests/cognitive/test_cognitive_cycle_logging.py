"""Tests for cognitive cycle step-level logging."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from loguru import logger
import pytest

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import PerceptionResult, PipelineStepResult, StepStatus
from iris.cognitive.cycle.service import CognitiveCycle
from iris.contracts.actions import ActionPlan
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import ObservationId, SessionId

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame


type _LoguruSink = Callable[[object], None]


def _observation() -> ActorMessageObservation:
    """Build a simple actor message observation for tests.

    Returns:
        ActorMessageObservation: Observation with a stable id.
    """
    return ActorMessageObservation(
        observation_id=ObservationId("obs-log-1"),
        session_id=SessionId("session-log-1"),
        context=ObservationContext(),
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
    )


class _RecordingStep:
    """Pipeline step that records invocations and returns a configured result."""

    def __init__(self, name: str, result: PipelineStepResult) -> None:
        self.name = name
        self._result = result
        self.invocations = 0

    async def run(self, frame: WorkspaceFrame) -> PipelineStepResult:
        """Return the pre-configured result and bump the invocation counter."""
        _ = frame
        self.invocations += 1
        return self._result


class _FailingStep:
    """Pipeline step that raises an exception to exercise the error log path."""

    def __init__(self, name: str, exc: BaseException) -> None:
        self.name = name
        self._exc = exc

    async def run(self, frame: WorkspaceFrame) -> PipelineStepResult:
        """Raise the pre-configured exception."""
        _ = frame
        raise self._exc


@dataclass
class _CapturedLog:
    """Container for a single captured loguru formatted message."""

    rendered: str


def _build_sink(captured: list[_CapturedLog]) -> _LoguruSink:
    """Build a loguru sink that appends rendered messages to the buffer.

    Args:
        captured: Mutable list used as the capture buffer.

    Returns:
        A sink callable compatible with ``logger.add``.
    """

    def _append(message: object) -> None:
        rendered = str(message).rstrip("\n")
        captured.append(_CapturedLog(rendered=rendered))

    return _append


def _make_capture_with_format(format_spec: str) -> tuple[list[_CapturedLog], int]:
    """Add a loguru sink with the given format and return the buffer + handler id.

    Args:
        format_spec: The loguru format string for the sink.

    Returns:
        Tuple of (capture buffer, handler id) for later cleanup.
    """
    captured: list[_CapturedLog] = []
    handler_id: int = logger.add(
        _build_sink(captured),
        level="DEBUG",
        format=format_spec,
    )
    return captured, handler_id


@pytest.fixture
def captured_logs() -> Iterator[list[_CapturedLog]]:
    """Fixture that exposes a list populated with formatted loguru records.

    Yields:
        A list of :class:`_CapturedLog` records with rendered text.
    """
    captured, handler_id = _make_capture_with_format("{message} | step={extra[step]}")
    try:
        yield captured
    finally:
        logger.remove(handler_id)


def _fallback_plan() -> ActionPlan:
    return ActionPlan(
        turn_intent="no_action",
        candidate_text=None,
        should_respond=False,
        priority=-1,
    )


@pytest.mark.anyio
async def test_run_logs_step_start_and_complete(captured_logs: list[_CapturedLog]) -> None:
    """CognitiveCycle は各ステップの start / complete を INFO でログ出力する。"""
    step = _RecordingStep(
        name="perception",
        result=PerceptionResult(step_name="perception", status=StepStatus.OK, text="hi"),
    )
    cycle = CognitiveCycle(
        steps=(step,),
        frame_builder=FrameBuilder(),
        fallback_plan=_fallback_plan(),
    )

    await cycle.run(_observation())

    rendered = [log.rendered for log in captured_logs]
    start_renders = [r for r in rendered if "cognitive.step.start" in r]
    complete_renders = [r for r in rendered if "cognitive.step.complete" in r]
    assert len(start_renders) == 1
    assert len(complete_renders) == 1
    assert "step=perception" in start_renders[0]
    assert "step=perception" in complete_renders[0]


@pytest.mark.anyio
async def test_run_logs_step_complete_includes_status() -> None:
    """CognitiveCycle は complete ログに status を含む。"""
    step = _RecordingStep(
        name="perception",
        result=PerceptionResult(step_name="perception", status=StepStatus.OK, text="hi"),
    )
    cycle = CognitiveCycle(
        steps=(step,),
        frame_builder=FrameBuilder(),
        fallback_plan=_fallback_plan(),
    )

    captured, handler_id = _make_capture_with_format(
        "{message} | step={extra[step]} | status={extra[status]}"
    )
    try:
        await cycle.run(_observation())
    finally:
        logger.remove(handler_id)

    complete_logs = [log for log in captured if "cognitive.step.complete" in log.rendered]
    assert len(complete_logs) == 1
    assert "status=ok" in complete_logs[0].rendered


@pytest.mark.anyio
async def test_run_logs_step_error_and_reraises() -> None:
    """CognitiveCycle はステップ例外時に error ログを出力し例外を再送出する。"""

    class _BoomError(Exception):
        pass

    failing_step = _FailingStep("broken", _BoomError("kaboom"))
    cycle = CognitiveCycle(
        steps=(failing_step,),
        frame_builder=FrameBuilder(),
        fallback_plan=_fallback_plan(),
    )

    captured, handler_id = _make_capture_with_format(
        "{message} | step={extra[step]} | et={extra[error_type]} | msg={extra[error_message]}"
    )
    try:
        with pytest.raises(_BoomError, match="kaboom"):
            await cycle.run(_observation())
    finally:
        logger.remove(handler_id)

    error_logs = [log for log in captured if "cognitive.step.error" in log.rendered]
    assert len(error_logs) == 1
    rendered = error_logs[0].rendered
    assert "step=broken" in rendered
    assert "_BoomError" in rendered
    assert "kaboom" in rendered


@pytest.mark.anyio
async def test_run_emits_logs_in_step_order(captured_logs: list[_CapturedLog]) -> None:
    """CognitiveCycle は複数ステップを実行順にログ出力する。"""
    step_a = _RecordingStep(
        "alpha",
        PerceptionResult(step_name="alpha", status=StepStatus.OK, text="a"),
    )
    step_b = _RecordingStep(
        "beta",
        PerceptionResult(step_name="beta", status=StepStatus.OK, text="b"),
    )
    cycle = CognitiveCycle(
        steps=(step_a, step_b),
        frame_builder=FrameBuilder(),
        fallback_plan=_fallback_plan(),
    )

    await cycle.run(_observation())

    step_renders = [r for r in (log.rendered for log in captured_logs) if "step=" in r]
    assert len(step_renders) == 4
    assert "step=alpha" in step_renders[0]
    assert "step=alpha" in step_renders[1]
    assert "step=beta" in step_renders[2]
    assert "step=beta" in step_renders[3]


@pytest.mark.anyio
async def test_run_includes_observation_and_session_id() -> None:
    """CognitiveCycle は各ログに observation_id と session_id を含む。"""
    step = _RecordingStep(
        "context-aware",
        PerceptionResult(step_name="context-aware", status=StepStatus.OK, text="x"),
    )
    cycle = CognitiveCycle(
        steps=(step,),
        frame_builder=FrameBuilder(),
        fallback_plan=_fallback_plan(),
    )

    captured, handler_id = _make_capture_with_format(
        "{message} | obs={extra[observation_id]} | session={extra[session_id]}"
    )
    try:
        await cycle.run(_observation())
    finally:
        logger.remove(handler_id)

    complete_logs = [log for log in captured if "cognitive.step.complete" in log.rendered]
    assert len(complete_logs) == 1
    rendered = complete_logs[0].rendered
    assert "obs=obs-log-1" in rendered
    assert "session=session-log-1" in rendered
