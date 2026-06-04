"""Iris v0.1 target runtime entrypoint.

Usage:
    python main.py --text "hello"
    python main.py --text "hello" --llm fake
    python main.py --text "hello" --llm openai
    python main.py --text "hello" --llm ollama --model qwen3:8b
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from iris.runtime.cli import run_one_turn


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Iris v0.1 target runtime")
    parser.add_argument("--text", required=True, help="Input text for one-turn interaction")
    parser.add_argument(
        "--llm",
        choices=("fake", "openai", "ollama"),
        default="fake",
        help="LLM backend (default: fake, deterministic)",
    )
    parser.add_argument("--model", default=None, help="Model name for provider-backed LLMs")
    parser.add_argument(
        "--ollama-host",
        default=None,
        help="Ollama host URL (only with --llm ollama)",
    )
    return parser.parse_args()


def run() -> None:
    """Parse CLI arguments, run one turn, and print the response."""
    args = _parse_args()
    text: str = args.text
    llm: str = args.llm
    model: str | None = args.model
    ollama_host: str | None = args.ollama_host
    output_text = asyncio.run(run_one_turn(text, llm=llm, model=model, ollama_host=ollama_host))
    if output_text:
        sys.stdout.write(output_text + "\n")
    sys.exit(0)


if __name__ == "__main__":
    run()
