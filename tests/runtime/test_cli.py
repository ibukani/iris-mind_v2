"""Tests for the runtime CLI entrypoint."""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING, cast

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.ports import LLMClient, LLMRequest, LLMResponse
from iris.contracts.observations import ObservationKind
from iris.core.ids import ObservationId, SessionId
from iris.runtime import cli as cli_module
from iris.runtime.app import IrisApp
from iris.runtime.cli import build_app, build_observation, main, run_one_turn
from iris.runtime.wiring.app import wire_default_app
from iris.runtime.wiring.cognitive import wire_text_response_cognitive_cycle

if TYPE_CHECKING:
    from iris.runtime.config import IrisRuntimeConfig


@pytest.mark.anyio
async def test_run_one_turn_returns_deterministic_output() -> None:
    """Verify run_one_turn returns deterministic fake LLM output."""
    output = await run_one_turn("hello", llm="fake")

    assert output == "fake response: hello"


@pytest.mark.anyio
async def test_run_one_turn_uses_fake_by_default() -> None:
    """Verify omitted --llm uses default fake config."""
    output = await run_one_turn("hello")

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


def test_build_app_ollama_dispatches_through_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify --llm ollama, --model, and --ollama-host become config overrides."""
    captured: dict[str, IrisRuntimeConfig] = {}

    def _fake_build_app_from_config(config: IrisRuntimeConfig) -> IrisApp:
        captured["config"] = config
        return wire_default_app(FakeLLMClient())

    monkeypatch.setattr(cli_module, "build_app_from_config", _fake_build_app_from_config)

    app = build_app(
        "ollama",
        model="qwen3:8b",
        ollama_host="http://ollama.local:11434",
    )

    assert app is not None
    config = captured["config"]
    assert config.models.default_chat.provider == "ollama"
    assert config.models.default_chat.model == "qwen3:8b"
    assert config.ollama.base_url == "http://ollama.local:11434"


def test_build_app_model_override_changes_default_chat_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify --model overrides only models.default_chat.model."""
    captured: dict[str, IrisRuntimeConfig] = {}

    def _fake_build_app_from_config(config: IrisRuntimeConfig) -> IrisApp:
        captured["config"] = config
        return wire_default_app(FakeLLMClient())

    monkeypatch.setattr(cli_module, "build_app_from_config", _fake_build_app_from_config)

    app = build_app(model="chat-model")

    assert app is not None
    config = captured["config"]
    assert config.models.default_chat.model == "chat-model"
    assert config.models.fast_judge.model == "fake-llm"
    assert config.models.reasoning.model == "fake-llm"


def test_build_app_openai_dispatches_without_real_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify --llm openai dispatches through config without calling OpenAI."""
    captured: dict[str, IrisRuntimeConfig] = {}

    def _fake_build_app_from_config(config: IrisRuntimeConfig) -> IrisApp:
        captured["config"] = config
        return wire_default_app(FakeLLMClient())

    monkeypatch.setattr(cli_module, "build_app_from_config", _fake_build_app_from_config)

    app = build_app("openai", model="gpt-custom")

    assert app is not None
    config = captured["config"]
    assert config.models.default_chat.provider == "openai"
    assert config.models.default_chat.model == "gpt-custom"


def test_build_app_openai_without_model_uses_provider_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify --llm openai without --model keeps fake-llm sentinel in config."""
    captured: dict[str, IrisRuntimeConfig] = {}

    def _fake_build_app_from_config(config: IrisRuntimeConfig) -> IrisApp:
        captured["config"] = config
        return wire_default_app(FakeLLMClient())

    monkeypatch.setattr(cli_module, "build_app_from_config", _fake_build_app_from_config)

    app = build_app("openai")

    assert app is not None
    config = captured["config"]
    assert config.models.default_chat.provider == "openai"
    assert config.models.default_chat.model == "fake-llm"


def test_build_app_default_creates_fake_app() -> None:
    """Verify build_app with no overrides creates a fake-backed app."""
    app = build_app()

    assert app is not None


def test_build_observation_structure() -> None:
    """Verify build_observation creates a structured ActorMessageObservation."""
    obs = build_observation("hello world")

    assert obs.text == "hello world"
    assert obs.kind == ObservationKind.ACTOR_MESSAGE
    assert obs.observation_id == ObservationId("cli-obs")
    assert obs.session_id == SessionId("cli-session")
    assert obs.context.actor is None
    assert obs.context.space_id is None
    assert obs.context.source == "cli"
    assert obs.occurred_at.tzinfo is not None


def test_build_observation_uses_utc_timezone() -> None:
    """Verify observation timestamp is in UTC."""
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
    """Verify main runs the CLI pipeline and writes output to stderr."""
    monkeypatch.setattr("sys.argv", ["cli", "--text", "hello", "--llm", "fake"])

    main()

    captured = capsys.readouterr()
    assert "fake response: hello" in captured.err


def test_main_uses_default_llm_backend(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify main defaults to fake backend when --llm is omitted."""
    monkeypatch.setattr("sys.argv", ["cli", "--text", "default"])

    main()

    captured = capsys.readouterr()
    assert "fake response: default" in captured.err


def test_main_help_describes_runtime_config_overrides(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify CLI help describes config and default_chat override semantics."""
    monkeypatch.setattr("sys.argv", ["cli", "--help"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert ".iris/config/llm.toml" in captured.out
    assert "models.default_chat.provider" in captured.out
    assert "models.default_chat.model" in captured.out
    assert "ollama.base_url" in captured.out


def test_main_with_openai_backend(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify main --llm openai dispatches through config without real API."""
    stub = cast("LLMClient", _StubOpenAILLM())
    captured: dict[str, IrisRuntimeConfig] = {}

    def _fake_build_app_from_config(config: IrisRuntimeConfig) -> IrisApp:
        captured["config"] = config
        cycle = wire_text_response_cognitive_cycle(
            stub,
            model=config.models.default_chat.model,
        )
        return IrisApp(cycle=cycle)

    monkeypatch.setattr(cli_module, "build_app_from_config", _fake_build_app_from_config)
    monkeypatch.setattr("sys.argv", ["cli", "--text", "ping", "--llm", "openai"])

    main()

    captured_output = capsys.readouterr()
    assert "openai response: ping" in captured_output.err
    assert captured["config"].models.default_chat.provider == "openai"


class _StubOpenAILLM:
    """A stub LLMClient that returns a canned OpenAI-like response."""

    @staticmethod
    async def generate(request: LLMRequest) -> LLMResponse:
        """Return a canned response referencing the last message content."""
        last = request.messages[-1]
        return LLMResponse(text=f"openai response: {last.content}", model=request.model)
