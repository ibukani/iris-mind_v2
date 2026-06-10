"""E2E pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio for gRPC E2E tests.

    Returns:
        AnyIO backend name.
    """
    return "asyncio"
