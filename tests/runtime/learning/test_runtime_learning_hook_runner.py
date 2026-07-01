"""RuntimeLearningHookRunner tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from loguru import logger
import pytest

from iris.contracts.actions import PresentedOutput
from iris.contracts.learning import RuntimeLearningEvent, RuntimeLearningEventKind
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import ObservationId, SessionId
from iris.runtime.learning.hooks import RuntimeLearningHookRunner

pytestmark = pytest.mark.anyio

if TYPE_CHECKING:
    from collections.abc import MutableSequence


class _RecordingRuntimeHook:
    def __init__(self, name: str, calls: MutableSequence[str], *, fail: bool = False) -> None:
        self._name = name
        self._calls = calls
        self._fail = fail

    async def after_runtime_event(self, event: RuntimeLearningEvent) -> None:
        _ = event
        self._calls.append(self._name)
        if self._fail:
            message = f"{self._name} failed"
            raise RuntimeError(message)


def _event() -> RuntimeLearningEvent:
    observation = ActorMessageObservation(
        observation_id=ObservationId("obs-runtime-learning"),
        session_id=SessionId("session-1"),
        context=ObservationContext(),
        occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="hello",
    )
    return RuntimeLearningEvent(
        kind=RuntimeLearningEventKind.INLINE_RESPONSE_GENERATED,
        observation=observation,
        output=PresentedOutput(text="hello"),
        occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
        route="cognitive",
        source_observation_id=observation.observation_id,
    )


async def test_runtime_hooks_run_in_order_and_failure_isolated() -> None:
    """登録順を維持し、障害をログして後続runtime hookを実行する。"""
    calls: list[str] = []
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(str(message)))
    try:
        await RuntimeLearningHookRunner(
            (
                _RecordingRuntimeHook("first", calls),
                _RecordingRuntimeHook("broken", calls, fail=True),
                _RecordingRuntimeHook("last", calls),
            )
        ).run(_event())
    finally:
        logger.remove(sink_id)

    assert calls == ["first", "broken", "last"]
    assert any("runtime learning hook failed" in message for message in messages)


async def test_empty_runtime_hook_list_is_valid() -> None:
    """空のruntime hook集合を許容する。"""
    await RuntimeLearningHookRunner(()).run(_event())
