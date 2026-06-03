"""Tests for the main.py target runtime entrypoint.
"""

from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_main_py_run_uses_target_runtime() -> None:
    from iris.runtime.cli import run_one_turn

    output = await run_one_turn("hello from main", llm="fake")
    assert output == "fake response: hello from main"


def test_main_py_module_imports_safely() -> None:
    import main as main_module

    assert hasattr(main_module, "run")
    assert callable(main_module.run)
