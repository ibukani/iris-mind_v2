"""v0.1 target runtime CLI entrypoint.

This is a thin adapter around target runtime wiring.

Usage:
    python -m iris.runtime.cli --text "hello"
    python -m iris.runtime.cli --text "hello" --llm fake
    python -m iris.runtime.cli --text "hello" --llm openai
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import sys
from typing import TYPE_CHECKING

from iris.adapters.llm.ollama import OllamaConfig
from iris.contracts.observations import ObservationKind, UserMessageObservation
from iris.core.ids import ObservationId, SessionId
from iris.runtime.wiring.app import (
    wire_default_app,
    wire_fake_app,
    wire_ollama_app,
    wire_openai_app,
)

if TYPE_CHECKING:
    from iris.runtime.app import IrisApp


def build_observation(text: str) -> UserMessageObservation:
    """Build a user message observation from plain text.

    Args:
        text: The user input text.

    Returns:
        A UserMessageObservation with a fixed session and observation ID.
    """
    return UserMessageObservation(
        observation_id=ObservationId("cli-obs"),
        session_id=SessionId("cli-session"),
        actor=None,
        space_id=None,
        occurred_at=datetime.now(UTC),
        kind=ObservationKind.USER_MESSAGE,
        text=text,
    )


def build_app(
    llm: str,
    *,
    model: str | None = None,
    ollama_host: str | None = None,
) -> IrisApp:
    """指定されたLLMバックエンド用のIrisAppを構築する.

    Args:
        llm: Backend name ('fake' or 'openai').
        model: Optional model name override for provider-backed LLMs.
        ollama_host: Optional Ollama host URL override.

    Returns:
        A wired IrisApp instance.
    """
    if llm == "fake":
        return wire_fake_app()
    if llm == "openai":
        return wire_openai_app(model=model or "gpt-5-mini")
    if llm == "ollama":
        config = OllamaConfig()
        return wire_ollama_app(
            model=model or config.model,
            base_url=ollama_host or config.base_url,
        )
    return wire_default_app()


async def run_one_turn(
    text: str,
    llm: str = "fake",
    *,
    model: str | None = None,
    ollama_host: str | None = None,
) -> str | None:
    """単一の対話ターンを実行し、応答テキストを返す.

    Args:
        text: User input text.
        llm: LLM backend name.
        model: Optional model name override for provider-backed LLMs.
        ollama_host: Optional Ollama host URL override.

    Returns:
        Response text, or None if no response was produced.
    """
    obs = build_observation(text)
    app = build_app(llm, model=model, ollama_host=ollama_host)
    output = await app.process_observation(obs)
    return output.text


def main() -> None:
    """CLI引数をパースし、1ターンの対話を実行する."""
    parser = argparse.ArgumentParser(description="Iris v0.1 target runtime — one-turn CLI")
    parser.add_argument("--text", required=True, help="Input text for one-turn interaction")
    parser.add_argument(
        "--llm",
        choices=("fake", "openai", "ollama"),
        default="fake",
        help="LLM backend (default: fake, deterministic; 'openai' requires OPENAI_API_KEY)",
    )
    parser.add_argument("--model", default=None, help="Model name for provider-backed LLMs")
    parser.add_argument(
        "--ollama-host",
        default=None,
        help="Ollama host URL (only with --llm ollama)",
    )

    args = parser.parse_args()
    text: str = args.text
    llm: str = args.llm
    model: str | None = args.model
    ollama_host: str | None = args.ollama_host

    output_text = asyncio.run(run_one_turn(text, llm=llm, model=model, ollama_host=ollama_host))
    if output_text:
        sys.stderr.write(output_text + "\n")


if __name__ == "__main__":
    main()
