"""LearningHookRunner tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from loguru import logger
import pytest

from iris.contracts.actions import ActionResult, ActionStatus, SendMessageAction
from iris.contracts.learning import LearningEvent
from iris.core.ids import ActionId, CorrelationId, SessionId
from iris.runtime.learning.hooks import LearningHookRunner

pytestmark = pytest.mark.anyio

if TYPE_CHECKING:
    from collections.abc import MutableSequence


class _RecordingHook:
    def __init__(self, name: str, calls: MutableSequence[str], *, fail: bool = False) -> None:
        self._name = name
        self._calls = calls
        self._fail = fail

    async def after_action_result(self, event: LearningEvent) -> None:
        _ = event
        self._calls.append(self._name)
        if self._fail:
            message = f"{self._name} failed"
            raise RuntimeError(message)


def _event() -> LearningEvent:
    action = SendMessageAction(
        action_id=ActionId("action-1"),
        session_id=SessionId("session-1"),
        correlation_id=CorrelationId("correlation-1"),
        text="hello",
    )
    return LearningEvent(
        result=ActionResult(
            action_id=action.action_id,
            correlation_id=action.correlation_id,
            status=ActionStatus.SUCCEEDED,
        ),
        delivery=None,
        action=action,
        target=None,
        reported_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def test_hooks_run_in_order_and_failure_isolated() -> None:
    """登録順を維持し、障害をログして後続フックを実行する。"""
    calls: list[str] = []
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(str(message)))
    try:
        await LearningHookRunner(
            (
                _RecordingHook("first", calls),
                _RecordingHook("broken", calls, fail=True),
                _RecordingHook("last", calls),
            )
        ).run(_event())
    finally:
        logger.remove(sink_id)
    assert calls == ["first", "broken", "last"]
    assert any("learning hook failed" in message for message in messages)


async def test_empty_hook_list_is_valid() -> None:
    """空のフック集合を許容する。"""
    await LearningHookRunner(()).run(_event())
