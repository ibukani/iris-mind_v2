"""Tests for the v0.1 target runtime CLI entrypoint.

These tests verify:
  - CLI runs one turn with fake LLM
  - CLI produces deterministic output
"""

from __future__ import annotations

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.contracts.observations import ObservationKind, UserMessageObservation
from iris.core.ids import ObservationId, SessionId
from iris.runtime.cli import build_app, build_observation, run_one_turn
from iris.runtime.wiring.app import wire_default_app


@pytest.mark.anyio
async def test_run_one_turn_returns_deterministic_output() -> None:
    output = await run_one_turn("hello", llm="fake")
    assert output == "fake response: hello"


@pytest.mark.anyio
async def test_run_one_turn_japanese_input() -> None:
    output = await run_one_turn("こんにちは", llm="fake")
    assert output is not None
    assert "こんにちは" in output


@pytest.mark.anyio
async def test_run_one_turn_empty_input() -> None:
    output = await run_one_turn("", llm="fake")
    assert output == "fake response: "


@pytest.mark.anyio
async def test_wire_default_app_runs_turn() -> None:
    app = wire_default_app()
    obs = build_observation("test message")
    output = await app.process_observation(obs)
    assert output.text == "fake response: test message"


@pytest.mark.anyio
async def test_build_app_fake_creates_app() -> None:
    app = build_app("fake")
    obs = UserMessageObservation(
        observation_id=ObservationId("test"),
        session_id=SessionId("test"),
        actor=None,
        occurred_at=__import__("datetime").datetime(2026, 6, 3),
        kind=ObservationKind.USER_MESSAGE,
        text="hi",
    )
    output = await app.process_observation(obs)
    assert output.text == "fake response: hi"


@pytest.mark.anyio
async def test_build_observation_structure() -> None:
    obs = build_observation("hello world")
    assert obs.text == "hello world"
    assert obs.kind == ObservationKind.USER_MESSAGE
    assert obs.observation_id == ObservationId("cli-obs")
    assert obs.session_id == SessionId("cli-session")


@pytest.mark.anyio
async def test_fake_llm_requests_are_recorded() -> None:
    llm = FakeLLMClient()
    app = wire_default_app(llm)
    obs = build_observation("record me")
    await app.process_observation(obs)
    assert len(llm.requests) == 1
    assert llm.requests[0].messages[-1].content == "record me"
