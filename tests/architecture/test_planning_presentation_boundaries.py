"""Architecture guard: planner must not own user-facing event reaction text."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PLANNER_PATH = PROJECT_ROOT / "iris" / "runtime" / "event_reaction" / "planner.py"

_USER_FACING_LITERALS: frozenset[str] = frozenset(
    {
        "Welcome back.",
        "Welcome back. I am here if you want to talk.",
    }
)


def test_event_reaction_planner_does_not_own_user_facing_templates() -> None:
    """planner.py はユーザー向けテンプレートテキストを保持してはならない。"""
    source = PLANNER_PATH.read_text()
    for literal in _USER_FACING_LITERALS:
        assert literal not in source, (
            f"planner.py contains user-facing literal {literal!r}; "
            "move it to iris/runtime/event_reaction/templates.py"
        )
