"""ランタイム設定メタデータの正規仕様。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from iris.runtime.config.errors import ConfigError

type ConfigValueType = Literal[
    "str",
    "int",
    "float",
    "bool",
    "enum",
    "optional_str",
    "optional_int",
    "optional_float",
]
type ConfigDefault = str | int | float | bool | None


@dataclass(frozen=True)
class ConfigFieldSpec:
    """1つのランタイム設定フィールドの機械可読メタデータ。"""

    path: str
    value_type: ConfigValueType
    default: ConfigDefault
    description: str
    toml: bool = True
    env: str | None = None
    cli: str | None = None
    secret: bool = False
    control_plane_editable: bool = True
    example: bool = True
    allowed_values: tuple[str, ...] = ()
    deprecated: bool = False


def runtime_config_specs() -> tuple[ConfigFieldSpec, ...]:
    """全ユーザー向けランタイム設定フィールドの正規仕様を返す。

    Returns:
        安定順序の設定フィールド仕様。
    """
    model_specs = tuple(
        spec
        for slot, max_tokens in (
            ("default_chat", 512),
            ("fast_judge", 128),
            ("reasoning", 1024),
        )
        for spec in (
            ConfigFieldSpec(
                f"models.{slot}.provider",
                "enum",
                "fake",
                f"{slot}モデルスロットのプロバイダ。",
                env=f"IRIS_{slot.upper()}_PROVIDER",
                allowed_values=("fake", "ollama", "openai"),
            ),
            ConfigFieldSpec(
                f"models.{slot}.model",
                "str",
                "fake-llm",
                f"{slot}モデルスロットのモデル名。",
                env=f"IRIS_{slot.upper()}_MODEL",
            ),
            ConfigFieldSpec(
                f"models.{slot}.temperature",
                "float",
                0.0,
                f"{slot}モデルスロットのtemperature。",
                env=f"IRIS_{slot.upper()}_TEMPERATURE",
            ),
            ConfigFieldSpec(
                f"models.{slot}.max_output_tokens",
                "optional_int",
                max_tokens,
                f"{slot}モデルスロットの最大出力トークン数。",
                env=f"IRIS_{slot.upper()}_MAX_OUTPUT_TOKENS",
            ),
        )
    )
    return (
        ConfigFieldSpec(
            "config.version",
            "int",
            1,
            "ランタイム設定ファイル形式のバージョン。",
            control_plane_editable=False,
        ),
        ConfigFieldSpec(
            "server.host",
            "str",
            "127.0.0.1",
            "gRPCサーバーのbind host。",
            env="IRIS_SERVER_HOST",
            cli="--host",
        ),
        ConfigFieldSpec(
            "server.port",
            "int",
            50051,
            "gRPCサーバーのbind port。",
            env="IRIS_SERVER_PORT",
            cli="--port",
        ),
        ConfigFieldSpec(
            path="server.local_only",
            value_type="bool",
            default=True,
            description="loopback hostのみを許可する。",
        ),
        ConfigFieldSpec(
            "server.shutdown_grace_seconds",
            "float",
            5.0,
            "gRPCサーバー停止時の猶予秒数。",
        ),
        ConfigFieldSpec(
            "state.backend",
            "enum",
            "memory",
            "ランタイム状態の永続化backend。",
            env="IRIS_STATE_BACKEND",
            allowed_values=("memory", "sqlite"),
        ),
        ConfigFieldSpec(
            "state.sqlite_path",
            "str",
            ".iris/runtime/state.sqlite3",
            "SQLite状態ファイルのパス。",
            env="IRIS_STATE_SQLITE_PATH",
        ),
        ConfigFieldSpec(
            "scheduler.enabled",
            "bool",
            default=False,
            description="RuntimeScheduler lifecycle loop を有効化する。",
        ),
        ConfigFieldSpec(
            "scheduler.interval_seconds",
            "float",
            30.0,
            "scheduler loop の実行間隔秒数。",
        ),
        ConfigFieldSpec(
            "scheduler.idle_threshold_seconds",
            "float",
            600.0,
            "IdleTickObservation を発火する idle 秒数。",
        ),
        ConfigFieldSpec(
            "scheduler.min_interval_per_target_seconds",
            "float",
            1800.0,
            "target ごとの proactive tick 最小間隔秒数。",
        ),
        ConfigFieldSpec(
            "scheduler.max_due_per_run",
            "int",
            10,
            "scheduler run 1回あたりの最大 due observation 数。",
        ),
        ConfigFieldSpec(
            "delivery.enabled",
            "bool",
            default=True,
            description="DeliveryOutbox と PollAppActions API を有効化する。",
        ),
        ConfigFieldSpec(
            "delivery.max_outbox_depth_per_provider",
            "int",
            100,
            "provider ごとの最大 outbox depth。",
        ),
        ConfigFieldSpec(
            "delivery.lease_seconds",
            "float",
            30.0,
            "PollAppActions が取得する lease 秒数。",
        ),
        ConfigFieldSpec(
            "delivery.max_attempts",
            "int",
            3,
            "配送 item ごとの最大試行回数。",
        ),
        ConfigFieldSpec(
            "delivery.retry_backoff_seconds",
            "float",
            30.0,
            "失敗後に retry 可能になるまでの秒数。",
        ),
        ConfigFieldSpec(
            "delivery.rate_limit_window_seconds",
            "float",
            1800.0,
            "DeliverySafetyGate の rate limit window 秒数。",
        ),
        ConfigFieldSpec(
            "delivery.quiet_hours.enabled",
            "bool",
            default=False,
            description="quiet hours による配送 block を有効化する。",
        ),
        ConfigFieldSpec(
            "delivery.quiet_hours.start",
            "str",
            "22:00",
            "quiet hours 開始 HH:MM。",
        ),
        ConfigFieldSpec(
            "delivery.quiet_hours.end",
            "str",
            "08:00",
            "quiet hours 終了 HH:MM。",
        ),
        ConfigFieldSpec(
            "delivery.quiet_hours.timezone",
            "str",
            "Asia/Tokyo",
            "quiet hours 判定 timezone。",
        ),
        *model_specs,
        ConfigFieldSpec(
            "ollama.base_url",
            "str",
            "http://localhost:11434",
            "Ollama APIのbase URL。",
            env="IRIS_OLLAMA_HOST",
        ),
        ConfigFieldSpec(
            "ollama.timeout_seconds",
            "float",
            120.0,
            "Ollama request timeout秒数。",
            env="IRIS_OLLAMA_TIMEOUT_SECONDS",
        ),
        ConfigFieldSpec(
            "ollama.keep_alive",
            "optional_str",
            None,
            "Ollamaモデルのkeep-alive指定。",
            env="IRIS_OLLAMA_KEEP_ALIVE",
        ),
        ConfigFieldSpec(
            "openai.model",
            "str",
            "gpt-5-mini",
            "OpenAI providerの既定モデル。",
            env="IRIS_OPENAI_MODEL",
        ),
        ConfigFieldSpec(
            "openai.timeout_seconds",
            "optional_float",
            None,
            "OpenAI request timeout秒数。",
            env="IRIS_OPENAI_TIMEOUT_SECONDS",
        ),
        ConfigFieldSpec(
            "openai.max_output_tokens",
            "optional_int",
            None,
            "OpenAI providerの最大出力トークン数。",
            env="IRIS_OPENAI_MAX_OUTPUT_TOKENS",
        ),
        ConfigFieldSpec(
            "logging.level",
            "enum",
            "INFO",
            "ランタイムログレベル。",
            env="IRIS_LOG_LEVEL",
            allowed_values=("TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        ),
        ConfigFieldSpec(
            "logging.format",
            "enum",
            "text",
            "ランタイムログ形式。",
            env="IRIS_LOG_FORMAT",
            allowed_values=("text", "json"),
        ),
        ConfigFieldSpec(
            "logging.file_path",
            "optional_str",
            None,
            "任意のログ出力ファイルパス。",
            env="IRIS_LOG_FILE",
            example=False,
        ),
        ConfigFieldSpec(
            "logging.rotation",
            "str",
            "10 MB",
            "ログファイルrotation指定。",
        ),
        ConfigFieldSpec(
            "logging.retention",
            "str",
            "7 days",
            "ログファイルretention指定。",
        ),
        ConfigFieldSpec(
            "safety.mode",
            "enum",
            "development",
            "出力safety gateの動作モード。",
            env="IRIS_SAFETY_MODE",
            allowed_values=("development", "basic"),
        ),
        ConfigFieldSpec(
            "safety.max_output_chars",
            "int",
            4000,
            "出力可能な最大文字数。",
            env="IRIS_SAFETY_MAX_OUTPUT_CHARS",
        ),
        ConfigFieldSpec(
            "diagnostics.mode",
            "enum",
            "warn",
            "起動時 LLM プロバイダ診断の動作モード。",
            env="IRIS_DIAGNOSTICS_MODE",
            allowed_values=("off", "warn", "strict"),
        ),
        ConfigFieldSpec(
            "diagnostics.timeout_seconds",
            "float",
            5.0,
            "診断チェック 1 件あたりのタイムアウト秒数。",
            env="IRIS_DIAGNOSTICS_TIMEOUT_SECONDS",
        ),
        ConfigFieldSpec(
            "diagnostics.warmup_models",
            "bool",
            default=False,
            description="診断後に provider 固有の warmup を実行する。",
            env="IRIS_DIAGNOSTICS_WARMUP_MODELS",
        ),
    )


def runtime_config_specs_for_version(version: int) -> tuple[ConfigFieldSpec, ...]:
    """指定versionに対応するランタイム設定仕様を返す。

    Args:
        version: TOMLから読み取った設定version。

    Returns:
        指定versionの設定フィールド仕様。

    Raises:
        ConfigError: versionが未対応の場合。
    """
    if version == 1:
        return runtime_config_specs()
    message = f"Unsupported runtime config version: {version}. Supported version: 1"
    raise ConfigError(message)
