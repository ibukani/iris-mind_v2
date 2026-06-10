"""E2E pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio for gRPC E2E tests.

    Returns:
        AnyIO backend name.
    """
    return "asyncio"


@pytest.fixture
def repo_root() -> Path:
    """Resolve the repository root for subprocess execution.

    Returns:
        Repository root path.
    """
    return Path(__file__).resolve().parents[2]
