"""ランタイム設定の最上位型・デフォルト・ロードエントリポイント。

優先順位は次のとおり:

1. 組み込みのデフォルト
2. TOML 設定ファイル
3. 環境変数
4. CLI オーバーライド

TOML は構造化された開発者向け設定。環境変数はシークレット、配置オーバーライド、
CI/コンテナ用オーバーライドを想定。CLI フラグは一時的な実験用オーバーライド。
以下のデフォルトは、他に何も設定されていない場合の安全なフォールバック。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
from typing import TYPE_CHECKING

from iris.runtime.config.auth import (
    RuntimeAuthConfig,
    apply_auth_env,
    apply_auth_toml,
    validate_auth_config,
)
from iris.runtime.config.conversation import (
    RuntimeConversationConfig,
    apply_conversation_toml,
    validate_conversation_config,
)
from iris.runtime.config.delivery import (
    RuntimeDeliveryConfig,
    apply_delivery_toml,
    validate_delivery_config,
)
from iris.runtime.config.diagnostics import (
    RuntimeDiagnosticsConfig,
    apply_diagnostics_env,
    apply_diagnostics_toml,
)
from iris.runtime.config.errors import ConfigError
from iris.runtime.config.learning import (
    RuntimeLearningConfig,
    apply_learning_toml,
    validate_learning_config,
)
from iris.runtime.config.llm import (
    LLMProvider,
    RuntimeModelsConfig,
    RuntimeOllamaConfig,
    RuntimeOpenAIConfig,
    default_runtime_models_config,
    validate_provider,
)
from iris.runtime.config.logging import RuntimeLoggingConfig
from iris.runtime.config.memory import RuntimeMemoryConfig, apply_memory_toml
from iris.runtime.config.observability import (
    RuntimeObservabilityConfig,
    apply_observability_toml,
    validate_observability_config,
)
from iris.runtime.config.parsing import (
    parse_raw_config_version,
    table_or_empty,
    validate_toml_keys,
)
from iris.runtime.config.safety import RuntimeSafetyConfig, apply_safety_env, apply_safety_toml
from iris.runtime.config.scheduler import (
    RuntimeSchedulerConfig,
    apply_scheduler_env,
    apply_scheduler_toml,
    validate_scheduler_config,
)
from iris.runtime.config.server import (
    RuntimeServerConfig,
    apply_server_env,
    apply_server_toml,
    validate_server_config,
    validate_server_port,
)
from iris.runtime.config.sources import apply_env as apply_llm_logging_env
from iris.runtime.config.sources import apply_toml as apply_llm_logging_toml
from iris.runtime.config.sources import read_toml_file
from iris.runtime.config.spec import runtime_config_specs_for_version
from iris.runtime.config.state import (
    RuntimeStateBackend,
    RuntimeStateConfig,
    apply_state_env,
    apply_state_toml,
    validate_state_config,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.runtime.config.parsing import TomlTable

_PROJECT_CONFIG_PATH = Path(".iris/config/runtime.toml")
_ENV_CONFIG_KEY = "IRIS_MIND_CONFIG"
_XDG_CONFIG_PATH = Path("iris-mind/runtime.toml")
_SUPPORTED_CONFIG_VERSION = 1


@dataclass(frozen=True)
class RuntimeConfigMetadata:
    """ランタイム設定ファイル自体のメタデータ。"""

    version: int = _SUPPORTED_CONFIG_VERSION


@dataclass(frozen=True)
class IrisRuntimeConfig:
    """アプリケーションワイヤリングが利用するランタイム設定。"""

    config: RuntimeConfigMetadata
    server: RuntimeServerConfig
    state: RuntimeStateConfig
    models: RuntimeModelsConfig
    ollama: RuntimeOllamaConfig
    openai: RuntimeOpenAIConfig
    logging: RuntimeLoggingConfig
    safety: RuntimeSafetyConfig
    auth: RuntimeAuthConfig
    diagnostics: RuntimeDiagnosticsConfig
    scheduler: RuntimeSchedulerConfig
    delivery: RuntimeDeliveryConfig
    learning: RuntimeLearningConfig
    memory: RuntimeMemoryConfig
    conversation: RuntimeConversationConfig
    observability: RuntimeObservabilityConfig


@dataclass(frozen=True)
class RuntimeConfigOverrides:
    """ランタイム初期化時に渡される設定オーバーライド。"""

    llm: LLMProvider | None = None
    model: str | None = None
    ollama_host: str | None = None
    server_host: str | None = None
    server_port: int | None = None


def default_runtime_config() -> IrisRuntimeConfig:
    """デフォルトのランタイム設定を構築する。

    Returns:
        デフォルトのランタイム設定。
    """
    return IrisRuntimeConfig(
        config=RuntimeConfigMetadata(),
        server=RuntimeServerConfig(),
        state=RuntimeStateConfig(),
        models=default_runtime_models_config(),
        ollama=RuntimeOllamaConfig(),
        openai=RuntimeOpenAIConfig(),
        logging=RuntimeLoggingConfig(),
        safety=RuntimeSafetyConfig(),
        auth=RuntimeAuthConfig(),
        diagnostics=RuntimeDiagnosticsConfig(),
        scheduler=RuntimeSchedulerConfig(),
        delivery=RuntimeDeliveryConfig(),
        learning=RuntimeLearningConfig(),
        memory=RuntimeMemoryConfig(),
        conversation=RuntimeConversationConfig(),
        observability=RuntimeObservabilityConfig(),
    )


def load_runtime_config(
    config_path: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    overrides: RuntimeConfigOverrides | None = None,
    cwd: Path | None = None,
) -> IrisRuntimeConfig:
    """デフォルト・TOML・環境変数・オーバーライドからランタイム設定を読み込む。

    Args:
        config_path: 任意の明示的 TOML ファイルパス。
        env: 環境変数のマッピング。デフォルトは ``os.environ``。
        overrides: 任意のオーバーライド値。
        cwd: 相対 config path と default discovery の基準ディレクトリ。

    Returns:
        検証済みのランタイム設定。

    Raises:
        ConfigError: 設定ファイル、値、version、keyが不正な場合。
    """
    config = default_runtime_config()
    runtime_env = os.environ if env is None else env
    runtime_cwd = Path.cwd() if cwd is None else cwd
    selected_config_path = resolve_runtime_config_path(
        config_path,
        cwd=runtime_cwd,
        env=runtime_env,
    )
    if selected_config_path is not None:
        try:
            table = read_toml_file(selected_config_path)
            version = parse_raw_config_version(table)
            specs = runtime_config_specs_for_version(version)
            validate_toml_keys(table, source=str(selected_config_path), specs=specs)
            config = _apply_toml(config, table)
        except ConfigError as exc:
            message = f"Runtime config error in {selected_config_path}: {exc}"
            raise ConfigError(message) from exc
    config = _apply_env(config, runtime_env)
    if overrides is not None:
        config = apply_runtime_overrides(config, overrides)
    return _validate_runtime_config(config)


def resolve_runtime_config_path(
    config_path: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> Path | None:
    """明示指定またはdefault discoveryから単一TOML sourceを解決する。

    Args:
        config_path: 任意の明示的TOMLファイルパス。
        env: discoveryに使う環境変数。
        cwd: 相対pathとproject discoveryの基準。

    Returns:
        選択された設定ファイル。見つからない場合は``None``。
    """
    runtime_cwd = Path.cwd() if cwd is None else cwd
    runtime_env = os.environ if env is None else env
    if config_path is not None:
        return normalize_config_path(config_path, cwd=runtime_cwd)
    return discover_default_config_path(cwd=runtime_cwd, env=runtime_env)


def normalize_config_path(path: str | Path, *, cwd: Path) -> Path:
    """設定ファイルパスを起動ディレクトリ基準の絶対パスへ正規化する。

    Args:
        path: 設定ファイルパス。
        cwd: 相対パスの基準ディレクトリ。

    Returns:
        正規化済みの設定ファイルパス。
    """
    expanded_path = Path(path).expanduser()
    if expanded_path.is_absolute():
        return expanded_path
    return cwd / expanded_path


def discover_default_config_path(
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path | None:
    """通常起動で利用する既定設定ファイルを決定的な順序で探す。

    Args:
        cwd: project-local config と相対 env path の基準ディレクトリ。
        env: default discovery に使う環境変数。
        home: home config 探索の基準ディレクトリ。

    Returns:
        最初に見つかった既定設定ファイル。見つからない場合は ``None``。

    Raises:
        ConfigError: ``IRIS_MIND_CONFIG`` が存在しない設定ファイルを指す場合。
    """
    runtime_cwd = Path.cwd() if cwd is None else cwd
    runtime_env = os.environ if env is None else env
    runtime_home = Path.home() if home is None else home

    project_config_path = runtime_cwd / _PROJECT_CONFIG_PATH
    if project_config_path.exists():
        return project_config_path

    env_config = runtime_env.get(_ENV_CONFIG_KEY)
    if env_config is not None:
        env_config_path = normalize_config_path(env_config, cwd=runtime_cwd)
        if env_config_path.exists():
            return env_config_path
        message = f"Runtime config file does not exist: {env_config_path}"
        raise ConfigError(message)

    config_candidates: list[Path] = []
    xdg_config_home = runtime_env.get("XDG_CONFIG_HOME")
    if xdg_config_home is not None:
        xdg_config_path = normalize_config_path(xdg_config_home, cwd=runtime_cwd)
        config_candidates.append(xdg_config_path / _XDG_CONFIG_PATH)
    config_candidates.append(runtime_home / ".config" / _XDG_CONFIG_PATH)
    for config_candidate in config_candidates:
        if config_candidate.exists():
            return config_candidate

    return None


def apply_runtime_overrides(
    config: IrisRuntimeConfig,
    overrides: RuntimeConfigOverrides,
) -> IrisRuntimeConfig:
    """既存ランタイム設定にオーバーライドを適用する。

    Args:
        config: ベースとなるランタイム設定。
        overrides: 適用するオーバーライド値。

    Returns:
        オーバーライド適用後のランタイム設定。
    """
    return _RuntimeConfigOverridePatch.from_overrides(overrides).apply(config)


def parse_llm_provider(value: str) -> LLMProvider:
    """LLM プロバイダ名を解析し検証する。

    Args:
        value: CLI または設定から渡されたプロバイダ名。

    Returns:
        型付けされたプロバイダ名。
    """
    return validate_provider(value, "models.default_chat.provider")


def all_model_slots_are_fake(config: IrisRuntimeConfig) -> bool:
    """全モデルスロットが fake プロバイダか判定する。

    開発・テスト用の判断に使う。

    Args:
        config: ランタイム設定。

    Returns:
        bool: 全モデルスロットが fake プロバイダなら True。
    """
    return (
        config.models.default_chat.provider == "fake"
        and config.models.fast_judge.provider == "fake"
        and config.models.reasoning.provider == "fake"
    )


def _apply_toml(config: IrisRuntimeConfig, table: TomlTable) -> IrisRuntimeConfig:
    """最上位 TOML テーブルをランタイム設定全体に適用する。

    Args:
        config: ベースとなるランタイム設定。
        table: 解析済みの最上位 TOML テーブル。

    Returns:
        TOML 値を反映したランタイム設定。
    """
    return _compose_runtime_config(
        config,
        _apply_toml_sections(config, table),
    )


def _apply_config_toml(table: TomlTable) -> RuntimeConfigMetadata:
    version = parse_raw_config_version({"config": table})
    return RuntimeConfigMetadata(version=version)


def _apply_toml_sections(
    config: IrisRuntimeConfig,
    table: TomlTable,
) -> _RuntimeConfigSections:
    """TOML テーブルから更新済み section 群を組み立てる。

    Args:
        config: ベースとなるランタイム設定。
        table: 解析済みの最上位 TOML テーブル。

    Returns:
        更新後の section 群。
    """
    config_table = table_or_empty(table, "config")
    server_table = table_or_empty(table, "server")
    state_table = table_or_empty(table, "state")
    scheduler_table = table_or_empty(table, "scheduler")
    delivery_table = table_or_empty(table, "delivery")
    safety_table = table_or_empty(table, "safety")
    auth_table = table_or_empty(table, "auth")
    diagnostics_table = table_or_empty(table, "diagnostics")
    models, ollama, openai, logging = apply_llm_logging_toml(
        config.models,
        config.ollama,
        config.openai,
        config.logging,
        table,
    )
    return _RuntimeConfigSections(
        config_metadata=_apply_config_toml(config_table),
        server=apply_server_toml(config.server, server_table),
        state=apply_state_toml(config.state, state_table),
        scheduler=apply_scheduler_toml(config.scheduler, scheduler_table),
        delivery=apply_delivery_toml(config.delivery, delivery_table),
        learning=apply_learning_toml(config.learning, table_or_empty(table, "learning")),
        memory=apply_memory_toml(config.memory, table_or_empty(table, "memory")),
        conversation=apply_conversation_toml(
            config.conversation,
            table_or_empty(table, "conversation"),
        ),
        observability=apply_observability_toml(
            config.observability,
            table_or_empty(table, "observability"),
        ),
        models=models,
        ollama=ollama,
        openai=openai,
        logging=logging,
        safety=apply_safety_toml(config.safety, safety_table),
        auth=apply_auth_toml(config.auth, auth_table),
        diagnostics=apply_diagnostics_toml(config.diagnostics, diagnostics_table),
    )


def _apply_env(
    config: IrisRuntimeConfig,
    env: Mapping[str, str],
) -> IrisRuntimeConfig:
    """ランタイム設定全体に環境変数オーバーライドを適用する。

    Args:
        config: ベースとなるランタイム設定。
        env: 環境変数のマッピング。

    Returns:
        環境変数値を反映したランタイム設定。
    """
    return _compose_runtime_config(
        config,
        _apply_env_sections(config, env),
    )


@dataclass(frozen=True)
class _RuntimeConfigSections:
    """TOML / ENV で更新した runtime section 群を束ねる。"""

    server: RuntimeServerConfig
    state: RuntimeStateConfig
    scheduler: RuntimeSchedulerConfig
    delivery: RuntimeDeliveryConfig
    learning: RuntimeLearningConfig
    memory: RuntimeMemoryConfig
    conversation: RuntimeConversationConfig
    models: RuntimeModelsConfig
    ollama: RuntimeOllamaConfig
    openai: RuntimeOpenAIConfig
    logging: RuntimeLoggingConfig
    safety: RuntimeSafetyConfig
    auth: RuntimeAuthConfig
    diagnostics: RuntimeDiagnosticsConfig
    observability: RuntimeObservabilityConfig
    config_metadata: RuntimeConfigMetadata | None = None


def _apply_env_sections(
    config: IrisRuntimeConfig,
    env: Mapping[str, str],
) -> _RuntimeConfigSections:
    """環境変数から更新済み section 群を組み立てる。

    Args:
        config: ベースとなるランタイム設定。
        env: 環境変数のマッピング。

    Returns:
        更新後の section 群。
    """
    models, ollama, openai, logging = apply_llm_logging_env(
        config.models, config.ollama, config.openai, config.logging, env
    )
    return _RuntimeConfigSections(
        server=apply_server_env(config.server, env),
        state=apply_state_env(config.state, env),
        scheduler=apply_scheduler_env(config.scheduler, env),
        delivery=config.delivery,
        learning=config.learning,
        memory=config.memory,
        conversation=config.conversation,
        observability=config.observability,
        models=models,
        ollama=ollama,
        openai=openai,
        logging=logging,
        safety=apply_safety_env(config.safety, env),
        auth=apply_auth_env(config.auth, env),
        diagnostics=apply_diagnostics_env(config.diagnostics, env),
    )


def _compose_runtime_config(
    config: IrisRuntimeConfig,
    sections: _RuntimeConfigSections,
) -> IrisRuntimeConfig:
    """更新済み section 群を 1 つの runtime config にまとめる。

    Args:
        config: ベースとなるランタイム設定。
        sections: 更新後の section 群。

    Returns:
        section 群を反映した runtime config。
    """
    metadata = config.config if sections.config_metadata is None else sections.config_metadata
    return replace(
        config,
        config=metadata,
        server=sections.server,
        state=sections.state,
        scheduler=sections.scheduler,
        delivery=sections.delivery,
        learning=sections.learning,
        memory=sections.memory,
        conversation=sections.conversation,
        observability=sections.observability,
        models=sections.models,
        ollama=sections.ollama,
        openai=sections.openai,
        logging=sections.logging,
        safety=sections.safety,
        auth=sections.auth,
        diagnostics=sections.diagnostics,
    )


def _validate_runtime_config(config: IrisRuntimeConfig) -> IrisRuntimeConfig:
    """ランタイム設定全体の後段検証をまとめて適用する。

    Args:
        config: 検証対象のランタイム設定。

    Returns:
        検証済みのランタイム設定。
    """
    validated_server = validate_server_config(config.server)
    validated_auth = validate_auth_config(
        auth=config.auth,
        server_local_only=validated_server.local_only,
        tls_enabled=validated_server.tls.enabled,
    )
    validated_state = validate_state_config(config.state)
    validated_scheduler = validate_scheduler_config(config.scheduler)
    validated_delivery = validate_delivery_config(config.delivery)
    validated_learning = validate_learning_config(config.learning)
    validated_conversation = validate_conversation_config(config.conversation)
    validated_observability = validate_observability_config(config.observability)
    _validate_transcript_backend(
        state=validated_state,
        conversation=validated_conversation,
    )
    return replace(
        config,
        server=validated_server,
        auth=validated_auth,
        state=validated_state,
        scheduler=validated_scheduler,
        delivery=validated_delivery,
        learning=validated_learning,
        conversation=validated_conversation,
        observability=validated_observability,
    )


def _validate_transcript_backend(
    *,
    state: RuntimeStateConfig,
    conversation: RuntimeConversationConfig,
) -> None:
    """Transcript persistence が silent no-op にならないことを検証する。

    Raises:
        ConfigError: transcript persistence が SQLite backend 以外で有効な場合。
    """
    if conversation.transcript.enabled and state.backend is not RuntimeStateBackend.SQLITE:
        message = "conversation.transcript.enabled=true requires state.backend='sqlite'"
        raise ConfigError(message)


@dataclass(frozen=True)
class _RuntimeConfigOverridePatch:
    """RuntimeConfigOverrides の optional 値を適用する。"""

    llm: LLMProvider | None = None
    model: str | None = None
    ollama_host: str | None = None
    server_host: str | None = None
    server_port: int | None = None

    @classmethod
    def from_overrides(cls, overrides: RuntimeConfigOverrides) -> _RuntimeConfigOverridePatch:
        """RuntimeConfigOverrides から patch を作る。

        Returns:
            取り出した override patch。
        """
        server_port = (
            validate_server_port(overrides.server_port, source="server_port override")
            if overrides.server_port is not None
            else None
        )
        return cls(
            llm=overrides.llm,
            model=overrides.model,
            ollama_host=overrides.ollama_host,
            server_host=overrides.server_host,
            server_port=server_port,
        )

    def apply(self, config: IrisRuntimeConfig) -> IrisRuntimeConfig:
        """ランタイム設定へ CLI override を適用する。

        Returns:
            オーバーライド適用後のランタイム設定。
        """
        models = config.models
        default_chat = models.default_chat
        if self.llm is not None:
            default_chat = replace(default_chat, provider=self.llm)
        if self.model is not None:
            default_chat = replace(default_chat, model=self.model)

        ollama = config.ollama
        if self.ollama_host is not None:
            ollama = replace(ollama, base_url=self.ollama_host)

        server = config.server
        if self.server_host is not None:
            server = replace(server, host=self.server_host)
        if self.server_port is not None:
            server = replace(server, port=self.server_port)
        validated_server = validate_server_config(server)
        return replace(
            config,
            server=validated_server,
            models=replace(models, default_chat=default_chat),
            ollama=ollama,
        )
