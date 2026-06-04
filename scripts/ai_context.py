# Copyright (c) 2026 Iris contributors
"""Print compact AI harness context for Iris coding agents."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]

CORE_FILES: tuple[str, ...] = (
    "AGENTS.md",
    "CLAUDE.md",
    ".agents/README.md",
    ".agents/rules/architecture.md",
    ".agents/rules/boundaries.md",
    ".agents/rules/cognitive-cycle.md",
    ".agents/rules/anti-patterns.md",
    ".agents/rules/typing.md",
    ".agents/rules/testing.md",
    ".agents/rules/ai-harness.md",
    ".agents/rules/verification.md",
)

WORKFLOWS: tuple[str, ...] = (
    ".agents/workflows/implement.md",
    ".agents/workflows/add-feature.md",
    ".agents/workflows/bugfix.md",
    ".agents/workflows/refactor.md",
    ".agents/workflows/review.md",
    ".agents/workflows/docs-update.md",
    ".agents/workflows/test-fix.md",
    ".agents/workflows/architecture.md",
    ".agents/workflows/ai-harness.md",
)

CHECKLISTS: tuple[str, ...] = (
    ".agents/checklists/pre-change.md",
    ".agents/checklists/done.md",
    ".agents/checklists/ai-harness.md",
    ".agents/checklists/failure-analysis.md",
)

COMMANDS: tuple[str, ...] = (
    "make ai-test-target TARGET=tests/path_or_file.py",
    "make ai-arch",
    "make ai-quick",
    "make ai-check",
    "make check",
)


def existing_paths(paths: Iterable[str]) -> list[str]:
    """Return paths that exist relative to the repository root."""
    return [path for path in paths if (REPO_ROOT / path).exists()]


def missing_paths(paths: Iterable[str]) -> list[str]:
    """Return paths that do not exist relative to the repository root."""
    return [path for path in paths if not (REPO_ROOT / path).exists()]


def write_section(title: str, lines: Iterable[str]) -> None:
    """Write a markdown-like section to stdout."""
    sys.stdout.write(f"## {title}\n")
    for line in lines:
        sys.stdout.write(f"- {line}\n")
    sys.stdout.write("\n")


def main() -> int:
    """Run the AI context command.

    Returns:
        Zero when all expected instruction files exist; otherwise one.
    """
    write_section("Core instruction files", existing_paths(CORE_FILES))
    write_section("Task workflows", existing_paths(WORKFLOWS))
    write_section("Checklists", existing_paths(CHECKLISTS))
    write_section("Verification commands", COMMANDS)

    missing = missing_paths((*CORE_FILES, *WORKFLOWS, *CHECKLISTS))
    if missing:
        write_section("Missing expected files", missing)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
