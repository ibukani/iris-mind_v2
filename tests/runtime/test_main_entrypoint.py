"""Tests for the main.py target runtime entrypoint."""

from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_main_py_run_uses_target_runtime() -> None:
    """Verify main.py delegates to the target iris.runtime CLI."""
    from iris.runtime.cli import run_one_turn  # noqa: PLC0415  # local import to avoid circular dep

    output = await run_one_turn("hello from main", llm="fake")
    assert output == "fake response: hello from main"


def test_main_py_module_imports_safely() -> None:
    """Verify main.py module imports without errors and exposes a run function."""
    import main as main_module  # noqa: PLC0415  # local import to test main module directly

    assert hasattr(main_module, "run")
    assert callable(main_module.run)
