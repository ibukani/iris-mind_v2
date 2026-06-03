"""Repository verification entry point for Iris.

This script is intentionally small and deterministic so coding agents can use a
single command (`make check` or `make verify`) before reporting completion.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]

MYPY_TARGETS: tuple[str, ...] = ("iris", "tests", "scripts", "main.py")


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]
    full_only: bool = False


CHECKS: tuple[Check, ...] = (
    Check("lint", ("uv", "run", "ruff", "check", ".")),
    Check("format", ("uv", "run", "ruff", "format", "--check", ".")),
    Check("type", ("uv", "run", "mypy", *MYPY_TARGETS)),
    Check("pyright", ("uv", "run", "pyright", ".")),
    Check("architecture", ("uv", "run", "pytest", "tests/architecture", "-q")),
    Check("tests+coverage", ("uv", "run", "pytest", "tests/"), full_only=True),
)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Iris verification checks.")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip the full test suite and coverage gate. Still runs lint, format, mypy, pyright, and architecture tests.",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue running remaining checks after a failure.",
    )
    return parser.parse_args(argv)


def selected_checks(*, quick: bool) -> tuple[Check, ...]:
    if quick:
        return tuple(check for check in CHECKS if not check.full_only)
    return CHECKS


def run_check(check: Check) -> int:
    command_text = " ".join(check.command)
    print(f"\n==> {check.name}: {command_text}", flush=True)
    completed = subprocess.run(check.command, cwd=REPO_ROOT, check=False)
    if completed.returncode == 0:
        print(f"==> {check.name}: passed", flush=True)
    else:
        print(f"==> {check.name}: failed with exit code {completed.returncode}", flush=True)
    return completed.returncode


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    failures: list[tuple[str, int]] = []

    for check in selected_checks(quick=args.quick):
        exit_code = run_check(check)
        if exit_code != 0:
            failures.append((check.name, exit_code))
            if not args.keep_going:
                break

    if failures:
        print("\nVerification failed:", flush=True)
        for name, exit_code in failures:
            print(f"- {name}: exit code {exit_code}", flush=True)
        return 1

    print("\nVerification passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
