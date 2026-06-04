"""Architecture guard for pre-commit autofix policy."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PRE_COMMIT_PATH = PROJECT_ROOT / ".pre-commit-config.yaml"


def test_precommit_does_not_run_broad_ruff_autofix() -> None:
    """pre-commit should report Ruff failures, not auto-fix broad repository diffs."""
    text = PRE_COMMIT_PATH.read_text(encoding="utf-8")
    assert "args: [--fix]" not in text
    assert "--fix" not in text
