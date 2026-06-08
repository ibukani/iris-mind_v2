"""Shared subprocess runner for scripts to centralize S404 suppression.

Scripts run only fixed repository command tuples, so the ``subprocess``
import is isolated in this single helper module.
"""

from __future__ import annotations

import subprocess  # noqa: S404 -- scripts run only fixed repository command tuples
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


def run(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    check: bool = False,
    capture_output: bool = False,
    text: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a fixed command tuple via subprocess.

    Args:
        args: Command-line arguments as a fixed tuple.
        cwd: Optional working directory.
        check: Whether to raise on non-zero exit.
        capture_output: Whether to capture stdout/stderr.
        text: Whether to return text instead of bytes.

    Returns:
        CompletedProcess result.
    """
    return subprocess.run(
        args,
        cwd=cwd,
        check=check,
        capture_output=capture_output,
        text=text,
    )
