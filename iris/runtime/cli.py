"""v0.1 target runtime CLI entrypoint.

Usage:
    python -m iris.runtime.cli --text "hello"
    python -m iris.runtime.cli --text "hello" --llm fake
    python -m iris.runtime.cli --text "hello" --llm openai
    python -m iris.runtime.cli --text "hello" --llm ollama --model qwen3:8b
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import sys
from typing import TYPE_CHECKING

from iris.contracts.observations import ObservationKind, UserMessageObservation
from iris.core.ids import ObservationId, SessionId
from iris.runtime.config import (
    CliConfigOverrides,
    load_runtime_config,
    parse_llm_provider,
)
from iris.runtime.wiring.app import build_app_from_config

if TYPE_CHECKING:
    from iris.runtime.app import IrisApp


def build_observation(text: str) -> UserMessageObservation:
    """入力テキストからCLI用UserMessageObservationを構築する.

    Args:
        text: User input text.

    Returns:
        A UserMessageObservation with a fixed session and observation ID.
    """
    return UserMessageObservation(
        observation_id=ObservationId("cli-obs"),
        session_id=SessionId("cli-session"),
        occurred_at=datetime.now(UTC),
        kind=ObservationKind.USER_MESSAGE,
        text=text,
        actor=None,
        space_id=None,
    )


def build_app(
    llm: str | None = None,
    *,
    model: str | None = None,
    ollama_host: str | None = None,
    config_path: str | None = None,
) -> IrisApp:
    """指定された設定からIrisAppを構築する.

    Args:
        llm: Optional default_chat provider override.
        model: Optional default_chat model override.
        ollama_host: Optional Ollama host URL override.
        config_path: Optional explicit TOML config path.

    Returns:
        A wired IrisApp instance.
    """
    provider = parse_llm_provider(llm) if llm is not None else None
    config = load_runtime_config(
        config_path,
        cli_overrides=CliConfigOverrides(
            llm=provider,
            model=model,
            ollama_host=ollama_host,
        ),
    )
    return build_app_from_config(config)


async def run_one_turn(
    text: str,
    llm: str | None = None,
    *,
    model: str | None = None,
    ollama_host: str | None = None,
    config_path: str | None = None,
) -> str | None:
    """単一の対話ターンを実行し、応答テキストを返す.

    Args:
        text: User input text.
        llm: Optional default_chat provider override.
        model: Optional default_chat model override.
        ollama_host: Optional Ollama host URL override.
        config_path: Optional explicit TOML config path.

    Returns:
        Response text, or None if no response was produced.
    """
    obs = build_observation(text)
    app = build_app(llm, model=model, ollama_host=ollama_host, config_path=config_path)
    output = await app.process_observation(obs)
    return output.text


def main() -> None:
    """CLI引数をパースし、1ターンの対話を実行する."""
    parser = argparse.ArgumentParser(description="Iris v0.1 — one-turn CLI")
    parser.add_argument("--text", required=True, help="Input text for one-turn interaction")
    parser.add_argument(
        "--llm",
        choices=("fake", "openai", "ollama"),
        default=None,
        help="Override models.default_chat.provider: fake, openai, or ollama",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override models.default_chat.model",
    )
    parser.add_argument(
        "--ollama-host",
        default=None,
        help="Override ollama.base_url",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Explicit runtime TOML config path, usually .iris/config/llm.toml",
    )

    args = parser.parse_args()
    text: str = args.text
    llm: str | None = args.llm
    model: str | None = args.model
    ollama_host: str | None = args.ollama_host
    config_path: str | None = args.config

    output_text = asyncio.run(
        run_one_turn(
            text,
            llm=llm,
            model=model,
            ollama_host=ollama_host,
            config_path=config_path,
        )
    )
    if output_text:
        sys.stderr.write(output_text + "\n")


if __name__ == "__main__":
    main()
