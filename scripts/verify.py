"""Repository verification entry point for Iris.

This script is intentionally small and deterministic so coding agents can use a
single command (`make check` or `make verify`) before reporting completion.

Failure analysis is integrated directly: when a check fails, the script prints
its failure class, the first failing file or test, and the recommended next
command.  This replaces the manual `.agents/checklists/failure-analysis.md`
steps with an automated, repeatable diagnostic.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._subprocess_runner import run as _run_command

MYPY_TARGETS: tuple[str, ...] = ("iris", "tests", "scripts", "main.py")
DEFAULT_TEST_TARGETS: tuple[str, ...] = (
    "tests/adapters",
    "tests/architecture",
    "tests/cognitive",
    "tests/contracts",
    "tests/core",
    "tests/features",
    "tests/presentation",
    "tests/runtime",
    "tests/scripts",
    "tests/test_oneturn_flow.py",
)
COVERAGE_ARGS: tuple[str, ...] = (
    "--cov=iris",
    "--cov-branch",
    "--cov-report=term-missing:skip-covered",
    "--cov-report=html",
    "--cov-fail-under=90",
)

RECOMMENDATIONS: dict[str, str] = {
    "lint": "make lint-fix  OR  uv run ruff check .",
    "format": "make format-write  OR  uv run ruff format .",
    "type": "make type  OR  uv run mypy iris tests scripts main.py",
    "pyright": "make pyright  OR  uv run pyright .",
    "architecture": "make arch  OR  uv run pytest tests/architecture -q",
    "tests+coverage": ("make ai-test-target TARGET=<failing_test>  OR  make coverage"),
    "environment": "Check uv environment and tool versions with make doctor",
}


@dataclass(frozen=True)
class Check:
    """A single verification check with name, command, and scope."""

    name: str
    command: tuple[str, ...]
    full_only: bool = False
    failure_class: str = "environment"


CHECKS: tuple[Check, ...] = (
    Check("lint", ("uv", "run", "ruff", "check", "."), failure_class="lint"),
    Check(
        "format",
        ("uv", "run", "ruff", "format", "--check", "."),
        failure_class="format",
    ),
    Check("type", ("uv", "run", "mypy", *MYPY_TARGETS), failure_class="type"),
    Check(
        "pyright",
        ("uv", "run", "pyright", "."),
        failure_class="pyright",
    ),
    Check(
        "architecture",
        ("uv", "run", "pytest", "tests/architecture", "-q"),
        failure_class="architecture",
    ),
    Check(
        "tests+coverage",
        ("uv", "run", "pytest", *DEFAULT_TEST_TARGETS, *COVERAGE_ARGS),
        full_only=True,
        failure_class="tests+coverage",
    ),
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


def _first_failing_location(stdout: str) -> str | None:
    """Extract the first failing file or test from tool stdout.

    Args:
        stdout: Captured standard output from the check command.

    Returns:
        File path (with optional line number) or pytest node id, or None.
    """
    # pytest: FAILED tests/path.py::test_name
    match = re.search(r"FAILED\s+(\S+)", stdout)
    if match:
        return match.group(1)
    # ruff / mypy / pyright: file.py:line:col ... or file.py:line: error:
    match = re.search(r"(.+?\.py):(\d+):", stdout)
    if match:
        return f"{match.group(1)}:{match.group(2)}"
    # ruff format --check lists plain filenames that need reformatting.
    match = re.search(r"(\S+\.py)", stdout)
    if match:
        return match.group(1)
    return None


def run_check(check: Check) -> int:
    """Execute a single verification check via subprocess.

    Captures stdout so that, on failure, an automated failure-analysis
    block can be printed: failure class, first failing location, and the
    recommended focused next command.  This mirrors the manual checklist
    in ``.agents/checklists/failure-analysis.md``.

    Args:
        check: The check to run.

    Returns:
        Exit code from the check (0 for success).
    """
    command_text = " ".join(check.command)
    sys.stdout.write(f"\n==> {check.name}: {command_text}\n")
    sys.stdout.flush()
    completed = _run_command(
        check.command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 0:
        sys.stdout.write(f"==> {check.name}: passed\n")
    else:
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        if stdout:
            sys.stdout.write(stdout)
        if stderr:
            sys.stdout.write(stderr)
        location = _first_failing_location(stdout)
        recommendation = RECOMMENDATIONS.get(check.failure_class, "")
        sys.stdout.write(f"\n==> {check.name}: failed with exit code {completed.returncode}\n")
        sys.stdout.write(f"    class: {check.failure_class}\n")
        if location:
            sys.stdout.write(f"    first failure: {location}\n")
        if recommendation:
            sys.stdout.write(f"    next: {recommendation}\n")
        sys.stdout.write("    note: do not relax config to pass; fix code or tests instead.\n")
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
        sys.stdout.write("\nFailure-analysis summary:\n")
        for name, exit_code in failures:
            check_match = next((c for c in CHECKS if c.name == name), None)
            if check_match is not None:
                rec = RECOMMENDATIONS.get(check_match.failure_class, "")
                sys.stdout.write(f"- {name} ({check_match.failure_class}): {rec}\n")
            else:
                sys.stdout.write(f"- {name}: exit code {exit_code}\n")
        sys.stdout.flush()
        return 1

    sys.stdout.write("\nVerification passed.\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
