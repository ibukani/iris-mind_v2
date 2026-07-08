"""Shared pytest target lists for repository verification scripts."""

from __future__ import annotations

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
