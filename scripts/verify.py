"""Repository verification entry point for Iris.

This script is intentionally small and deterministic so coding agents can use a
single command (`make check` or `make verify`) before reporting completion.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess  # noqa: S404 -- local gate runs fixed repository command tuples only
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]

MYPY_TARGETS: tuple[str, ...] = ("iris", "tests", "scripts", "main.py")
COVERAGE_ARGS: tuple[str, ...] = (
    "--cov=iris",
    "--cov-branch",
    "--cov-report=term-missing:skip-covered",
    "--cov-report=html",
    "--cov-fail-under=90",
)


@dataclass(frozen=True)
class Check:
    """A single verification check with name, command, and scope."""

    name: str
    command: tuple[str, ...]
    full_only: bool = False


CHECKS: tuple[Check, ...] = (
    Check("lint", ("uv", "run", "ruff", "check", ".")),
    Check("format", ("uv", "run", "ruff", "format", "--check", ".")),
    Check("type", ("uv", "run", "mypy", *MYPY_TARGETS)),
    Check("pyright", ("uv", "run", "pyright", ".")),
    Check("architecture", ("uv", "run", "pytest", "tests/architecture", "-q")),
    Check("tests+coverage", ("uv", "run", "pytest", "tests/", *COVERAGE_ARGS), full_only=True),
)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments for the verification script.

    Args:
        argv: Command-line argument sequence.

    Returns:
        Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(description="Run Iris verification checks.")
    parser.add_argument(
        "--quick",
        action="store_true",
        help=(
            "Skip the full test suite and coverage gate. "
            "Still runs lint, format, mypy, pyright, and architecture tests."
        ),
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue running remaining checks after a failure.",
    )
    return parser.parse_args(argv)


def selected_checks(*, quick: bool) -> tuple[Check, ...]:
    """Filter checks based on the quick flag.

    Args:
        quick: If True, skip full-only checks (tests+coverage).

    Returns:
        Tuple of checks to run.
    """
    if quick:
        return tuple(check for check in CHECKS if not check.full_only)
    return CHECKS


def run_check(check: Check) -> int:
    """Execute a single verification check via subprocess.

    Args:
        check: The check to run.

    Returns:
        Exit code from the check (0 for success).
    """
    command_text = " ".join(check.command)
    sys.stdout.write(f"\n==> {check.name}: {command_text}\n")
    sys.stdout.flush()
    completed = subprocess.run(check.command, cwd=REPO_ROOT, check=False)
    if completed.returncode == 0:
        sys.stdout.write(f"==> {check.name}: passed\n")
    else:
        sys.stdout.write(f"==> {check.name}: failed with exit code {completed.returncode}\n")
    sys.stdout.flush()
    return completed.returncode


def main(argv: Sequence[str] | None = None) -> int:
    """Run all verification checks and report results.

    Args:
        argv: Optional argument sequence; defaults to sys.argv[1:].

    Returns:
        0 if all checks passed, 1 otherwise.
    """
    args = parse_args(sys.argv[1:] if argv is None else argv)
    failures: list[tuple[str, int]] = []

    for check in selected_checks(quick=args.quick):
        exit_code = run_check(check)
        if exit_code != 0:
            failures.append((check.name, exit_code))
            if not args.keep_going:
                break

    if failures:
        sys.stdout.write("\nVerification failed:\n")
        for name, exit_code in failures:
            sys.stdout.write(f"- {name}: exit code {exit_code}\n")
        sys.stdout.flush()
        return 1

    sys.stdout.write("\nVerification passed.\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
