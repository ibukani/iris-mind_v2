"""ランタイム設定メタデータの正規仕様。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from iris.contracts.llm import DEFAULT_FAKE_LLM_MODEL
from iris.runtime.config.errors import ConfigError
from iris.runtime.config.model_slots import model_slot_specs


class ConfigValueType(StrEnum):
    """設定値の型。"""

    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    ENUM = "enum"
    OPTIONAL_STR = "optional_str"
    OPTIONAL_INT = "optional_int"
    OPTIONAL_FLOAT = "optional_float"


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


_RATE_LIMIT_RESERVED_DESC = (
    "予約済み: 現在の DeliverySafetyGate では未使用。"
    "プロアクティブ送信頻度は scheduler.min_interval_per_target_seconds で制御する。"
)


def runtime_config_specs() -> tuple[ConfigFieldSpec, ...]:
    """全ユーザー向けランタイム設定フィールドの正規仕様を返す。

    Returns:
        安定順序の設定フィールド仕様。
    """
    model_specs = tuple(
        spec
        for slot in model_slot_specs()
        for spec in (
            ConfigFieldSpec(
                f"models.{slot.name}.provider",
                ConfigValueType.ENUM,
                "fake",
                f"{slot.name}モデルスロットのプロバイダ。",
                env=f"IRIS_{slot.name.upper()}_PROVIDER",
                allowed_values=("fake", "ollama", "openai"),
            ),
            ConfigFieldSpec(
                f"models.{slot.name}.model",
                ConfigValueType.STR,
                DEFAULT_FAKE_LLM_MODEL,
                f"{slot.name}モデルスロットのモデル名。",
                env=f"IRIS_{slot.name.upper()}_MODEL",
            ),
            ConfigFieldSpec(
                f"models.{slot.name}.temperature",
                ConfigValueType.FLOAT,
                0.0,
                f"{slot.name}モデルスロットのtemperature。",
                env=f"IRIS_{slot.name.upper()}_TEMPERATURE",
            ),
            ConfigFieldSpec(
                f"models.{slot.name}.max_output_tokens",
                ConfigValueType.OPTIONAL_INT,
                slot.default_max_output_tokens,
                f"{slot.name}モデルスロットの最大出力トークン数。",
                env=f"IRIS_{slot.name.upper()}_MAX_OUTPUT_TOKENS",
            ),
        )
    )
    return (
        ConfigFieldSpec(
            "config.version",
            ConfigValueType.INT,
            1,
            "ランタイム設定ファイル形式のバージョン。",
            control_plane_editable=False,
        ),
        ConfigFieldSpec(
            "server.host",
            ConfigValueType.STR,
            "127.0.0.1",
            "gRPCサーバーのbind host。",
            env="IRIS_SERVER_HOST",
            cli="--host",
        ),
        ConfigFieldSpec(
            "server.port",
            ConfigValueType.INT,
            50051,
            "gRPCサーバーのbind port。",
            env="IRIS_SERVER_PORT",
            cli="--port",
        ),
        ConfigFieldSpec(
            path="server.local_only",
            value_type=ConfigValueType.BOOL,
            default=True,
            description="loopback hostのみを許可する。",
        ),
        ConfigFieldSpec(
            "server.shutdown_grace_seconds",
            ConfigValueType.FLOAT,
            5.0,
            "gRPCサーバー停止時の猶予秒数。",
        ),
        ConfigFieldSpec(
            "learning.enabled",
            ConfigValueType.BOOL,
            default=True,
            description="配送結果後の学習 dispatch を有効化する。",
        ),
        ConfigFieldSpec(
            "learning.background_jobs_enabled",
            ConfigValueType.BOOL,
            default=True,
            description="バックグラウンドジョブループを有効化する。",
        ),
        ConfigFieldSpec(
            "learning.background_job_interval_seconds",
            ConfigValueType.FLOAT,
            10.0,
            "バックグラウンドジョブ実行間隔秒数。",
        ),
        ConfigFieldSpec(
            "learning.max_jobs_per_run",
            ConfigValueType.INT,
            5,
            "1回のバックグラウンド処理上限件数。",
        ),
        ConfigFieldSpec(
            "learning.max_attempts",
            ConfigValueType.INT,
            3,
            "学習ジョブの既定最大試行回数。",
        ),
        ConfigFieldSpec(
            "server.tls.enabled",
            ConfigValueType.BOOL,
            default=False,
            description="gRPC server TLS を有効化する。",
        ),
        ConfigFieldSpec(
            "server.tls.cert_chain_path",
            ConfigValueType.OPTIONAL_STR,
            None,
            "TLS certificate chain path。",
        ),
        ConfigFieldSpec(
            "server.tls.private_key_path",
            ConfigValueType.OPTIONAL_STR,
            None,
            "TLS private key path。",
            secret=True,
            control_plane_editable=False,
            example=False,
        ),
        ConfigFieldSpec(
            "server.tls.client_ca_path",
            ConfigValueType.OPTIONAL_STR,
            None,
            "Optional mTLS client CA path。",
        ),
        ConfigFieldSpec(
            "server.tls.require_client_cert",
            ConfigValueType.BOOL,
            default=False,
            description="gRPC TLS client certificate を要求する。",
        ),
        ConfigFieldSpec(
            "auth.mode",
            ConfigValueType.ENUM,
            "local_dev",
            "Runtime RPC auth mode。",
            env="IRIS_RUNTIME_AUTH_MODE",
            allowed_values=("local_dev", "required"),
        ),
        ConfigFieldSpec(
            "auth.allow_unauthenticated_loopback",
            ConfigValueType.BOOL,
            default=True,
            description="local_dev loopback の unauthenticated RPC を許可する。",
        ),
        ConfigFieldSpec(
            "auth.require_tls_for_remote",
            ConfigValueType.BOOL,
            default=True,
            description="(非推奨) remote bind では TLS が常に要求されます。",
            control_plane_editable=False,
        ),
        ConfigFieldSpec(
            "auth.allow_insecure_remote",
            ConfigValueType.BOOL,
            default=False,
            description="開発用に remote insecure bind を明示許可する。",
            control_plane_editable=False,
        ),
        ConfigFieldSpec(
            "auth.static_tokens_env",
            ConfigValueType.STR,
            "IRIS_RUNTIME_TOKENS",
            "Static bearer token hashes を読む環境変数名。",
            secret=True,
            control_plane_editable=False,
            example=False,
        ),
        ConfigFieldSpec(
            "state.backend",
            ConfigValueType.ENUM,
            "memory",
            "ランタイム状態の永続化backend。",
            env="IRIS_STATE_BACKEND",
            allowed_values=("memory", "sqlite"),
        ),
        ConfigFieldSpec(
            "state.sqlite_path",
            ConfigValueType.STR,
            ".iris/runtime/state.sqlite3",
            "SQLite状態ファイルのパス。",
            env="IRIS_STATE_SQLITE_PATH",
        ),
        ConfigFieldSpec(
            "memory.vector.enabled",
            ConfigValueType.BOOL,
            default=False,
            description="SQLite memory の hybrid vector retrieval を有効化する。",
        ),
        ConfigFieldSpec(
            "memory.vector.backend",
            ConfigValueType.ENUM,
            "in_memory",
            "派生 vector index backend。",
            allowed_values=("in_memory", "qdrant"),
        ),
        ConfigFieldSpec(
            "memory.vector.collection",
            ConfigValueType.STR,
            "iris_memory",
            "vector index collection 名。",
        ),
        ConfigFieldSpec(
            "memory.vector.rebuild_on_startup",
            ConfigValueType.BOOL,
            default=True,
            description="起動時に正本 MemoryStore から index を同期する。",
        ),
        ConfigFieldSpec(
            "memory.vector.fail_open_on_index_error",
            ConfigValueType.BOOL,
            default=True,
            description="index 障害時も canonical memory write を保持する。",
        ),
        ConfigFieldSpec(
            "memory.embedding.provider",
            ConfigValueType.ENUM,
            "fake",
            "memory embedding provider。",
            allowed_values=("fake",),
        ),
        ConfigFieldSpec(
            "memory.embedding.model",
            ConfigValueType.STR,
            "fake-v1",
            "embedding model 識別子。",
        ),
        ConfigFieldSpec(
            "memory.embedding.dimension",
            ConfigValueType.INT,
            32,
            "embedding vector 次元数。",
        ),
        ConfigFieldSpec(
            "memory.embedding.batch_size",
            ConfigValueType.INT,
            32,
            "rebuild 時の embedding batch size。",
        ),
        ConfigFieldSpec(
            "memory.vector.qdrant.url",
            ConfigValueType.STR,
            "http://localhost:6333",
            "Qdrant REST endpoint。",
        ),
        ConfigFieldSpec(
            "memory.vector.qdrant.api_key_env",
            ConfigValueType.OPTIONAL_STR,
            None,
            "Qdrant API key を読む環境変数名。",
            example=False,
        ),
        ConfigFieldSpec(
            "memory.vector.qdrant.prefer_grpc",
            ConfigValueType.BOOL,
            default=False,
            description="Qdrant gRPC transport 選択予約。現在は REST のみ。",
        ),
        ConfigFieldSpec(
            "scheduler.enabled",
            ConfigValueType.BOOL,
            default=False,
            description="RuntimeScheduler lifecycle loop を有効化する。",
        ),
        ConfigFieldSpec(
            "scheduler.interval_seconds",
            ConfigValueType.FLOAT,
            30.0,
            "scheduler loop の実行間隔秒数。",
        ),
        ConfigFieldSpec(
            "scheduler.idle_threshold_seconds",
            ConfigValueType.FLOAT,
            600.0,
            "IdleTickObservation を発火する idle 秒数。",
        ),
        ConfigFieldSpec(
            "scheduler.min_interval_per_target_seconds",
            ConfigValueType.FLOAT,
            1800.0,
            "target ごとの proactive tick 最小間隔秒数。",
        ),
        ConfigFieldSpec(
            "scheduler.target_stale_after_seconds",
            ConfigValueType.FLOAT,
            604800.0,
            "target が stale になるまでの idle 秒数 (デフォルト7日)。",
            env="IRIS_SCHEDULER_TARGET_STALE_AFTER_SECONDS",
        ),
        ConfigFieldSpec(
            "scheduler.max_due_per_run",
            ConfigValueType.INT,
            10,
            "scheduler run 1回あたりの最大 due observation 数。",
        ),
        ConfigFieldSpec(
            "delivery.enabled",
            ConfigValueType.BOOL,
            default=True,
            description="DeliveryOutbox と PollAppActions API を有効化する。",
        ),
        ConfigFieldSpec(
            "delivery.max_outbox_depth_per_provider",
            ConfigValueType.INT,
            100,
            "provider ごとの最大 outbox depth。",
        ),
        ConfigFieldSpec(
            "delivery.lease_seconds",
            ConfigValueType.FLOAT,
            30.0,
            "PollAppActions が取得する lease 秒数。",
        ),
        ConfigFieldSpec(
            "delivery.max_attempts",
            ConfigValueType.INT,
            3,
            "配送 item ごとの最大試行回数。",
        ),
        ConfigFieldSpec(
            "delivery.retry_backoff_seconds",
            ConfigValueType.FLOAT,
            30.0,
            "失敗後に retry 可能になるまでの秒数。",
        ),
        ConfigFieldSpec(
            "delivery.rate_limit_window_seconds",
            ConfigValueType.FLOAT,
            1800.0,
            _RATE_LIMIT_RESERVED_DESC,
        ),
        ConfigFieldSpec(
            "delivery.quiet_hours.enabled",
            ConfigValueType.BOOL,
            default=False,
            description="quiet hours による配送 block を有効化する。",
        ),
        ConfigFieldSpec(
            "delivery.quiet_hours.start",
            ConfigValueType.STR,
            "22:00",
            "quiet hours 開始 HH:MM。",
        ),
        ConfigFieldSpec(
            "delivery.quiet_hours.end",
            ConfigValueType.STR,
            "08:00",
            "quiet hours 終了 HH:MM。",
        ),
        ConfigFieldSpec(
            "delivery.quiet_hours.timezone",
            ConfigValueType.STR,
            "Asia/Tokyo",
            "quiet hours 判定 timezone。",
        ),
        *model_specs,
        ConfigFieldSpec(
            "ollama.base_url",
            ConfigValueType.STR,
            "http://localhost:11434",
            "Ollama APIのbase URL。",
            env="IRIS_OLLAMA_HOST",
        ),
        ConfigFieldSpec(
            "ollama.timeout_seconds",
            ConfigValueType.FLOAT,
            120.0,
            "Ollama request timeout秒数。",
            env="IRIS_OLLAMA_TIMEOUT_SECONDS",
        ),
        ConfigFieldSpec(
            "ollama.keep_alive",
            ConfigValueType.OPTIONAL_STR,
            None,
            "Ollamaモデルのkeep-alive指定。",
            env="IRIS_OLLAMA_KEEP_ALIVE",
        ),
        ConfigFieldSpec(
            "ollama.think",
            ConfigValueType.OPTIONAL_STR,
            default=False,
            description="Ollamaの推論思考設定 (true/false/low/highなど)。",
            env="IRIS_OLLAMA_THINK",
        ),
        ConfigFieldSpec(
            "openai.model",
            ConfigValueType.STR,
            "gpt-5-mini",
            "OpenAI providerの既定モデル。",
            env="IRIS_OPENAI_MODEL",
        ),
        ConfigFieldSpec(
            "openai.timeout_seconds",
            ConfigValueType.OPTIONAL_FLOAT,
            None,
            "OpenAI request timeout秒数。",
            env="IRIS_OPENAI_TIMEOUT_SECONDS",
        ),
        ConfigFieldSpec(
            "openai.max_output_tokens",
            ConfigValueType.OPTIONAL_INT,
            None,
            "OpenAI providerの最大出力トークン数。",
            env="IRIS_OPENAI_MAX_OUTPUT_TOKENS",
        ),
        ConfigFieldSpec(
            "logging.level",
            ConfigValueType.ENUM,
            "INFO",
            "ランタイムログレベル。",
            env="IRIS_LOG_LEVEL",
            allowed_values=("TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        ),
        ConfigFieldSpec(
            "logging.format",
            ConfigValueType.ENUM,
            "text",
            "ランタイムログ形式。",
            env="IRIS_LOG_FORMAT",
            allowed_values=("text", "json"),
        ),
        ConfigFieldSpec(
            "logging.file_path",
            ConfigValueType.OPTIONAL_STR,
            None,
            "任意のログ出力ファイルパス。",
            env="IRIS_LOG_FILE",
            example=False,
        ),
        ConfigFieldSpec(
            "logging.rotation",
            ConfigValueType.STR,
            "10 MB",
            "ログファイルrotation指定。",
        ),
        ConfigFieldSpec(
            "logging.retention",
            ConfigValueType.STR,
            "7 days",
            "ログファイルretention指定。",
        ),
        ConfigFieldSpec(
            "safety.mode",
            ConfigValueType.ENUM,
            "development",
            "出力safety gateの動作モード。",
            env="IRIS_SAFETY_MODE",
            allowed_values=("development", "basic", "strict"),
        ),
        ConfigFieldSpec(
            "safety.max_output_chars",
            ConfigValueType.INT,
            4000,
            "出力可能な最大文字数。",
            env="IRIS_SAFETY_MAX_OUTPUT_CHARS",
        ),
        ConfigFieldSpec(
            "diagnostics.mode",
            ConfigValueType.ENUM,
            "warn",
            "起動時 LLM プロバイダ診断の動作モード。",
            env="IRIS_DIAGNOSTICS_MODE",
            allowed_values=("off", "warn", "strict"),
        ),
        ConfigFieldSpec(
            "diagnostics.timeout_seconds",
            ConfigValueType.FLOAT,
            5.0,
            "診断チェック 1 件あたりのタイムアウト秒数。",
            env="IRIS_DIAGNOSTICS_TIMEOUT_SECONDS",
        ),
        ConfigFieldSpec(
            "diagnostics.readiness_timeout_seconds",
            ConfigValueType.FLOAT,
            5.0,
            "readiness 診断チェックのタイムアウト秒数。",
            env="IRIS_DIAGNOSTICS_READINESS_TIMEOUT_SECONDS",
        ),
        ConfigFieldSpec(
            "diagnostics.warmup_timeout_seconds",
            ConfigValueType.FLOAT,
            120.0,
            "warmup 診断チェックのタイムアウト秒数。",
            env="IRIS_DIAGNOSTICS_WARMUP_TIMEOUT_SECONDS",
        ),
        ConfigFieldSpec(
            "diagnostics.warmup_models",
            ConfigValueType.BOOL,
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
