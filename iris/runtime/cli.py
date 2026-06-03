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

from iris.contracts.observations import ObservationKind, UserMessageObservation
from iris.core.ids import ObservationId, SessionId
from iris.runtime.app import IrisApp
from iris.runtime.wiring.app import wire_default_app, wire_fake_app, wire_openai_app


def build_observation(text: str) -> UserMessageObservation:
    return UserMessageObservation(
        observation_id=ObservationId("cli-obs"),
        session_id=SessionId("cli-session"),
        actor=None,
        occurred_at=datetime.now(UTC),
        kind=ObservationKind.USER_MESSAGE,
        text=text,
    )


def build_app(llm: str, *, model: str | None = None) -> IrisApp:
    if llm == "fake":
        return wire_fake_app()
    if llm == "openai":
        from iris.adapters.llm.openai import OpenAIConfig

        config = OpenAIConfig.from_env(model=model or "gpt-5-mini")
        return wire_openai_app(config)
    return wire_default_app()


async def run_one_turn(text: str, llm: str = "fake") -> str | None:
    obs = build_observation(text)
    app = build_app(llm)
    output = await app.process_observation(obs)
    return output.text


def main() -> None:
    parser = argparse.ArgumentParser(description="Iris v0.1 target runtime — one-turn CLI")
    parser.add_argument("--text", required=True, help="Input text for one-turn interaction")
    parser.add_argument(
        "--llm",
        choices=["fake", "openai"],
        default="fake",
        help="LLM backend (default: fake, deterministic; 'openai' requires OPENAI_API_KEY)",
    )
    parser.add_argument("--model", default=None, help="OpenAI model name (only with --llm openai)")

    args = parser.parse_args()

    output_text = asyncio.run(run_one_turn(args.text, llm=args.llm))
    if output_text:
        print(output_text)
    sys.exit(0)


if __name__ == "__main__":
    main()
