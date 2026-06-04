#!/usr/bin/env python3
"""Iris v0.1 target runtime entrypoint.

Usage:
    python main.py --text "hello"
    python main.py --text "hello" --llm fake
    python main.py --text "hello" --llm openai
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
        choices=("fake", "openai"),
        default="fake",
        help="LLM backend (default: fake, deterministic)",
    )
    parser.add_argument("--model", default=None, help="OpenAI model name (only with --llm openai)")
    return parser.parse_args()


def run() -> None:
    """Parse CLI arguments, run one turn, and print the response."""
    args = _parse_args()
    text: str = args.text
    llm: str = args.llm
    output_text = asyncio.run(run_one_turn(text, llm=llm))
    if output_text:
        sys.stdout.write(output_text + "\n")
    sys.exit(0)


if __name__ == "__main__":
    run()
