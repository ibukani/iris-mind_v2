"""会話履歴、transcript、long conversation policy のランタイム設定。"""

from __future__ import annotations

from dataclasses import dataclass, replace

from iris.runtime.config.parsing import TomlTable, parse_bool, parse_int, table_or_empty
from iris.runtime.config.validation import require_greater_than_zero, require_zero_or_greater


@dataclass(frozen=True)
class RuntimeTranscriptConfig:
    """Persistent transcript storage の設定。"""

    enabled: bool = False
    retention_days: int = 30
    max_records_per_key: int = 1000


@dataclass(frozen=True)
class RuntimeConversationConfig:
    """短期会話windowと長期会話圧縮の設定。"""

    max_window_records: int = 20
    max_history_chars: int = 8000
    summary_enabled: bool = True
    summary_max_chars: int = 1600
    summary_min_records: int = 12
    transcript: RuntimeTranscriptConfig = RuntimeTranscriptConfig()


def apply_conversation_toml(
    config: RuntimeConversationConfig,
    table: TomlTable,
) -> RuntimeConversationConfig:
    """`[conversation]` TOML 値を適用する。

    Returns:
        検証済み会話設定。
    """
    transcript = apply_transcript_toml(
        config.transcript,
        table_or_empty(table, "transcript", path="conversation.transcript"),
    )
    value = replace(config, transcript=transcript)
    if "max_window_records" in table:
        value = replace(
            value,
            max_window_records=parse_int(
                table["max_window_records"],
                "conversation.max_window_records",
            ),
        )
    if "max_history_chars" in table:
        value = replace(
            value,
            max_history_chars=parse_int(
                table["max_history_chars"],
                "conversation.max_history_chars",
            ),
        )
    if "summary_enabled" in table:
        value = replace(
            value,
            summary_enabled=parse_bool(
                table["summary_enabled"],
                "conversation.summary_enabled",
            ),
        )
    if "summary_max_chars" in table:
        value = replace(
            value,
            summary_max_chars=parse_int(
                table["summary_max_chars"],
                "conversation.summary_max_chars",
            ),
        )
    if "summary_min_records" in table:
        value = replace(
            value,
            summary_min_records=parse_int(
                table["summary_min_records"],
                "conversation.summary_min_records",
            ),
        )
    return validate_conversation_config(value)


def apply_transcript_toml(
    config: RuntimeTranscriptConfig,
    table: TomlTable,
) -> RuntimeTranscriptConfig:
    """`[conversation.transcript]` TOML 値を適用する。

    Returns:
        検証済み transcript 設定。
    """
    value = config
    if "enabled" in table:
        value = replace(
            value,
            enabled=parse_bool(table["enabled"], "conversation.transcript.enabled"),
        )
    if "retention_days" in table:
        value = replace(
            value,
            retention_days=parse_int(
                table["retention_days"],
                "conversation.transcript.retention_days",
            ),
        )
    if "max_records_per_key" in table:
        value = replace(
            value,
            max_records_per_key=parse_int(
                table["max_records_per_key"],
                "conversation.transcript.max_records_per_key",
            ),
        )
    return validate_transcript_config(value)


def validate_conversation_config(config: RuntimeConversationConfig) -> RuntimeConversationConfig:
    """会話設定の数値範囲を検証する。

    Returns:
        検証済み会話設定。
    """
    return replace(
        config,
        max_window_records=require_greater_than_zero(
            config.max_window_records,
            "conversation.max_window_records",
        ),
        max_history_chars=require_zero_or_greater(
            config.max_history_chars,
            "conversation.max_history_chars",
        ),
        summary_max_chars=require_zero_or_greater(
            config.summary_max_chars,
            "conversation.summary_max_chars",
        ),
        summary_min_records=require_greater_than_zero(
            config.summary_min_records,
            "conversation.summary_min_records",
        ),
        transcript=validate_transcript_config(config.transcript),
    )


def validate_transcript_config(config: RuntimeTranscriptConfig) -> RuntimeTranscriptConfig:
    """Transcript 設定の数値範囲を検証する。

    Returns:
        検証済み transcript 設定。
    """
    return replace(
        config,
        retention_days=require_zero_or_greater(
            config.retention_days,
            "conversation.transcript.retention_days",
        ),
        max_records_per_key=require_greater_than_zero(
            config.max_records_per_key,
            "conversation.transcript.max_records_per_key",
        ),
    )
