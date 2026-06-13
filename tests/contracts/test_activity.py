"""Activity contract tests."""

from __future__ import annotations

from iris.contracts.activity import ActivityKind


def test_activity_kind_exposes_non_message_external_events() -> None:
    """ActivityKindがclient-facing非message eventだけを持つことを確認する。"""
    assert {kind.value for kind in ActivityKind} == {
        "actor_typing_started",
        "actor_typing_stopped",
        "app_opened",
        "app_closed",
        "voice_joined",
        "voice_left",
        "system_interaction",
    }
