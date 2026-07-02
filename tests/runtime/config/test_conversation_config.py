"""Conversation runtime config tests。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from iris.runtime.config import ConfigError, load_runtime_config
from iris.runtime.config.conversation import RuntimeConversationConfig, apply_conversation_toml

if TYPE_CHECKING:
    from pathlib import Path

    from iris.runtime.config.parsing import TomlTable


def test_conversation_config_defaults_are_safe() -> None:
    """Transcript persistence はデフォルトで無効。"""
    config = RuntimeConversationConfig()

    assert config.max_window_records == 20
    assert config.transcript.enabled is False
    assert config.transcript.retention_days == 30


def test_conversation_config_loads_from_toml(tmp_path: Path) -> None:
    """Conversation TOML section を runtime config へ反映する。"""
    path = tmp_path / "runtime.toml"
    path.write_text(
        """
        [state]
        backend = "sqlite"
        sqlite_path = "{sqlite_path}"

        [conversation]
        max_window_records = 8
        max_history_chars = 1024
        summary_enabled = true
        summary_max_chars = 400
        summary_min_records = 5

        [conversation.transcript]
        enabled = true
        retention_days = 14
        max_records_per_key = 200
        """.format(sqlite_path=tmp_path / "state.sqlite3"),
        encoding="utf-8",
    )

    config = load_runtime_config(path)

    assert config.conversation.max_window_records == 8
    assert config.conversation.max_history_chars == 1024
    assert config.conversation.summary_max_chars == 400
    assert config.conversation.transcript.enabled is True
    assert config.conversation.transcript.retention_days == 14
    assert config.conversation.transcript.max_records_per_key == 200


def test_transcript_enabled_requires_sqlite_backend(tmp_path: Path) -> None:
    """Transcript persistence 有効化は SQLite backend を要求する。"""
    path = tmp_path / "runtime.toml"
    path.write_text(
        """
        [conversation.transcript]
        enabled = true
        """,
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=r"state\.backend='sqlite'"):
        load_runtime_config(path)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("max_window_records", 0),
        ("summary_min_records", 0),
        ("transcript.max_records_per_key", 0),
        ("max_history_chars", -1),
        ("summary_max_chars", -1),
        ("transcript.retention_days", -1),
    ],
)
def test_conversation_config_rejects_invalid_bounds(key: str, value: int) -> None:
    """会話設定の不正な数値範囲を拒否する。"""
    table = _table_for(key, value)

    with pytest.raises(ConfigError):
        apply_conversation_toml(RuntimeConversationConfig(), table)


def _table_for(key: str, value: int) -> TomlTable:
    if key.startswith("transcript."):
        return {"transcript": {key.removeprefix("transcript."): value}}
    return {key: value}
