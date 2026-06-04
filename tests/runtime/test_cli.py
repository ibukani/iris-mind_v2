"""Tests for the v0.1 target runtime CLI entrypoint.

These tests verify:
  - CLI runs one turn with fake LLM
  - CLI produces deterministic output
  - main() handles argument parsing and stderr output
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.ollama import OllamaConfig
from iris.adapters.llm.ports import LLMClient, LLMRequest, LLMResponse
from iris.contracts.observations import ObservationKind, UserMessageObservation
from iris.core.ids import ObservationId, SessionId
from iris.runtime import cli as cli_module
from iris.runtime.app import IrisApp
from iris.runtime.cli import build_app, build_observation, main, run_one_turn
from iris.runtime.wiring.app import wire_default_app
from iris.runtime.wiring.cognitive import wire_text_response_cognitive_cycle


@pytest.mark.anyio
async def test_run_one_turn_returns_deterministic_output() -> None:
    """Verify run_one_turn returns deterministic fake LLM output."""
    output = await run_one_turn("hello", llm="fake")
    assert output == "fake response: hello"


@pytest.mark.anyio
async def test_run_one_turn_japanese_input() -> None:
    """Verify run_one_turn handles Japanese input correctly."""
    output = await run_one_turn("こんにちは", llm="fake")
    assert output is not None
    assert "こんにちは" in output


@pytest.mark.anyio
async def test_run_one_turn_empty_input() -> None:
    """Verify run_one_turn handles empty input gracefully."""
    output = await run_one_turn("", llm="fake")
    assert output == "fake response: "


@pytest.mark.anyio
async def test_wire_default_app_runs_turn() -> None:
    """Verify wire_default_app creates a functional IrisApp."""
    app = wire_default_app()
    obs = build_observation("test message")
    output = await app.process_observation(obs)
    assert output.text == "fake response: test message"


@pytest.mark.anyio
async def test_build_app_fake_creates_app() -> None:
    """Verify build_app returns an IrisApp using fake LLM."""
    app = build_app("fake")
    obs = UserMessageObservation(
        observation_id=ObservationId("test"),
        session_id=SessionId("test"),
        actor=None,
        space_id=None,
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.USER_MESSAGE,
        text="hi",
    )
    output = await app.process_observation(obs)
    assert output.text == "fake response: hi"


def test_build_app_openai_dispatches_to_wire_openai_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify build_app with 'openai' dispatches to wire_openai_app."""
    called: dict[str, object] = {}

    def _fake_wire_openai_app(
        _config: object = None,
        *,
        model: str = "gpt-5-mini",
    ) -> IrisApp:
        """Record the model and return a fake IrisApp.

        Args:
            _config: Ignored; OpenAI config is provided by the caller.
            model: The model name passed through by build_app.

        Returns:
            IrisApp: A fake app backed by the fake LLM.
        """
        called["model"] = model
        cycle = wire_text_response_cognitive_cycle(FakeLLMClient())
        return IrisApp(cycle=cycle)

    monkeypatch.setattr(cli_module, "wire_openai_app", _fake_wire_openai_app)
    app = build_app("openai", model="gpt-custom")
    assert app is not None
    assert called.get("model") == "gpt-custom"


def test_build_app_ollama_dispatches_to_wire_ollama_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify build_app dispatches Ollama options without calling a real server."""
    called: dict[str, object] = {}

    def _fake_wire_ollama_app(
        config: OllamaConfig | None = None,
        *,
        model: str = "qwen3:8b",
        base_url: str = "http://localhost:11434",
    ) -> IrisApp:
        """Return a fake app and record Ollama wiring arguments."""
        called["config"] = config
        called["model"] = model
        called["base_url"] = base_url
        cycle = wire_text_response_cognitive_cycle(FakeLLMClient())
        return IrisApp(cycle=cycle)

    monkeypatch.setattr(cli_module, "wire_ollama_app", _fake_wire_ollama_app)

    app = build_app(
        "ollama",
        model="qwen3:8b",
        ollama_host="http://ollama.local:11434",
    )

    assert app is not None
    assert called.get("config") is None
    assert called.get("model") == "qwen3:8b"
    assert called.get("base_url") == "http://ollama.local:11434"


def test_build_app_ollama_uses_config_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify build_app uses OllamaConfig defaults when no overrides are passed."""
    called: dict[str, object] = {}

    def _fake_wire_ollama_app(
        config: OllamaConfig | None = None,
        *,
        model: str = "qwen3:8b",
        base_url: str = "http://localhost:11434",
    ) -> IrisApp:
        """Return a fake app and record default Ollama wiring arguments."""
        called["config"] = config
        called["model"] = model
        called["base_url"] = base_url
        cycle = wire_text_response_cognitive_cycle(FakeLLMClient())
        return IrisApp(cycle=cycle)

    monkeypatch.setattr(cli_module, "wire_ollama_app", _fake_wire_ollama_app)

    app = build_app("ollama")

    assert app is not None
    assert called.get("config") is None
    assert called.get("model") == OllamaConfig().model
    assert called.get("base_url") == OllamaConfig().base_url


def test_build_app_default_creates_default_app() -> None:
    """Verify build_app with an unknown backend falls back to the default app."""
    app = build_app("unknown-backend")
    assert app is not None


def test_build_observation_structure() -> None:
    """Verify build_observation creates a properly structured UserMessageObservation."""
    obs = build_observation("hello world")
    assert obs.text == "hello world"
    assert obs.kind == ObservationKind.USER_MESSAGE
    assert obs.observation_id == ObservationId("cli-obs")
    assert obs.session_id == SessionId("cli-session")
    assert obs.actor is None
    assert obs.space_id is None
    assert obs.occurred_at.tzinfo is not None


def test_build_observation_uses_utc_timezone() -> None:
    """Verify the observation timestamp is in UTC."""
    obs = build_observation("x")
    assert obs.occurred_at.tzinfo is not None
    assert obs.occurred_at.utcoffset() == UTC.utcoffset(obs.occurred_at)


@pytest.mark.anyio
async def test_fake_llm_requests_are_recorded() -> None:
    """Verify FakeLLMClient inside default app records the LLM request."""
    llm = FakeLLMClient()
    app = wire_default_app(llm)
    obs = build_observation("record me")
    await app.process_observation(obs)
    assert len(llm.requests) == 1
    assert llm.requests[0].messages[-1].content == "record me"


def test_main_writes_response_to_stderr(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify main() runs the CLI pipeline and writes output to stderr."""
    monkeypatch.setattr("sys.argv", ["cli", "--text", "hello", "--llm", "fake"])
    main()
    captured = capsys.readouterr()
    assert "fake response: hello" in captured.err


def test_main_uses_default_llm_backend(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify main() defaults to the fake LLM when --llm is not provided."""
    monkeypatch.setattr("sys.argv", ["cli", "--text", "default"])
    main()
    captured = capsys.readouterr()
    assert "fake response: default" in captured.err


class _StubOpenAILLM:
    """A stub LLMClient that returns a canned response."""

    @staticmethod
    async def generate(request: LLMRequest) -> LLMResponse:
        """Return a canned response referencing the last message content.

        Args:
            request: The LLM request whose last message is echoed.

        Returns:
            LLMResponse: A response with text "openai response: <content>".
        """
        last = request.messages[-1]
        return LLMResponse(text=f"openai response: {last.content}", model=request.model)


def test_main_with_openai_backend(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify main() with --llm openai dispatches to the OpenAI wiring path."""
    stub = cast("LLMClient", _StubOpenAILLM())
    called: dict[str, object] = {}

    def _fake_wire(
        _llm: str,
        *,
        model: str | None = None,
        ollama_host: str | None = None,
    ) -> IrisApp:
        """Build a fake IrisApp that uses the stub LLM.

        Args:
            _llm: Ignored; the backend name is not relevant for the stub.
            model: The model name to record in the call log.
            ollama_host: Unused Ollama host passthrough.

        Returns:
            IrisApp: An app backed by the stub LLM.
        """
        called["model"] = model
        called["ollama_host"] = ollama_host
        cycle = wire_text_response_cognitive_cycle(stub)
        return IrisApp(cycle=cycle)

    monkeypatch.setattr(cli_module, "build_app", _fake_wire)
    monkeypatch.setattr("sys.argv", ["cli", "--text", "ping", "--llm", "openai"])
    main()
    captured = capsys.readouterr()
    assert "openai response: ping" in captured.err
