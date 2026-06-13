"""Presence contract tests."""

from __future__ import annotations

from iris.contracts.presence import PresenceStatus


def test_presence_status_exposes_provider_visible_states() -> None:
    """PresenceStatusがprovider-visible状態を網羅することを確認する。"""
    assert {status.value for status in PresenceStatus} == {
        "unknown",
        "online",
        "offline",
        "away",
        "idle",
        "do_not_disturb",
        "invisible",
    }
