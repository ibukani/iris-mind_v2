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

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.llm import (
    LLMProvider,
    RuntimeModelConfig,
    RuntimeModelsConfig,
    RuntimeOllamaConfig,
    RuntimeOpenAIConfig,
    validate_provider,
)
from iris.runtime.config.logging import RuntimeLoggingConfig
from iris.runtime.config.parsing import parse_int, table_or_empty
from iris.runtime.config.safety import RuntimeSafetyConfig, apply_safety_env, apply_safety_toml
from iris.runtime.config.server import (
    RuntimeServerConfig,
    apply_server_env,
    apply_server_toml,
    validate_server_config,
    validate_server_port,
)
from iris.runtime.config.sources import apply_env, apply_toml, read_toml_file
from iris.runtime.config.state import (
    RuntimeStateConfig,
    apply_state_env,
    apply_state_toml,
    validate_state_config,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.runtime.config.parsing import TomlTable

_PROJECT_CONFIG_PATH = Path(".iris/config/runtime.toml")
_LEGACY_PROJECT_CONFIG_PATH = Path(".iris/config/llm.toml")
_ENV_CONFIG_KEY = "IRIS_MIND_CONFIG"
_XDG_CONFIG_PATH = Path("iris-mind/runtime.toml")
_LEGACY_XDG_CONFIG_PATH = Path("iris-mind/llm.toml")
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
        models=RuntimeModelsConfig(
            default_chat=RuntimeModelConfig(
                provider="fake",
                model="fake-llm",
                max_output_tokens=512,
            ),
            fast_judge=RuntimeModelConfig(
                provider="fake",
                model="fake-llm",
                max_output_tokens=128,
            ),
            reasoning=RuntimeModelConfig(
                provider="fake",
                model="fake-llm",
                max_output_tokens=1024,
            ),
        ),
        ollama=RuntimeOllamaConfig(),
        openai=RuntimeOpenAIConfig(),
        logging=RuntimeLoggingConfig(),
        safety=RuntimeSafetyConfig(),
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
            config = _apply_toml(config, read_toml_file(selected_config_path))
        except ConfigError as exc:
            message = f"Runtime config error in {selected_config_path}: {exc}"
            raise ConfigError(message) from exc
    config = _apply_env(config, runtime_env)
    if overrides is not None:
        config = apply_runtime_overrides(config, overrides)

    config = replace(config, server=validate_server_config(config.server))
    return replace(config, state=validate_state_config(config.state))


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

    for project_path in (_PROJECT_CONFIG_PATH, _LEGACY_PROJECT_CONFIG_PATH):
        project_config_path = runtime_cwd / project_path
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
        config_candidates.extend(
            (
                xdg_config_path / _XDG_CONFIG_PATH,
                xdg_config_path / _LEGACY_XDG_CONFIG_PATH,
            )
        )
    config_candidates.extend(
        (
            runtime_home / ".config" / _XDG_CONFIG_PATH,
            runtime_home / ".config" / _LEGACY_XDG_CONFIG_PATH,
        )
    )
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
    default_chat = config.models.default_chat
    if overrides.llm is not None:
        default_chat = replace(default_chat, provider=overrides.llm)
    if overrides.model is not None:
        default_chat = replace(default_chat, model=overrides.model)

    ollama = config.ollama
    if overrides.ollama_host is not None:
        ollama = replace(ollama, base_url=overrides.ollama_host)

    server = config.server
    if overrides.server_host is not None:
        server = replace(server, host=overrides.server_host)
    if overrides.server_port is not None:
        port = validate_server_port(overrides.server_port, source="server_port override")
        server = replace(server, port=port)

    return replace(
        config,
        server=server,
        models=replace(config.models, default_chat=default_chat),
        ollama=ollama,
    )


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
    metadata = _apply_config_toml(config.config, table_or_empty(table, "config"))
    server = apply_server_toml(config.server, table_or_empty(table, "server"))
    state = apply_state_toml(config.state, table_or_empty(table, "state"))
    safety = apply_safety_toml(config.safety, table_or_empty(table, "safety"))

    models, ollama, openai, logging = apply_toml(
        config.models,
        config.ollama,
        config.openai,
        config.logging,
        table,
    )
    return replace(
        config,
        config=metadata,
        server=server,
        state=state,
        models=models,
        ollama=ollama,
        openai=openai,
        logging=logging,
        safety=safety,
    )


def _apply_config_toml(
    config: RuntimeConfigMetadata,
    table: TomlTable,
) -> RuntimeConfigMetadata:
    version = config.version
    if "version" in table:
        version = parse_int(table["version"], "config.version")
    if version != _SUPPORTED_CONFIG_VERSION:
        message = (
            f"Unsupported runtime config version: {version}. "
            f"Supported version: {_SUPPORTED_CONFIG_VERSION}"
        )
        raise ConfigError(message)
    return RuntimeConfigMetadata(version=version)


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
    server = apply_server_env(config.server, env)
    state = apply_state_env(config.state, env)
    safety = apply_safety_env(config.safety, env)

    models, ollama, openai, logging = apply_env(
        config.models, config.ollama, config.openai, config.logging, env
    )
    return replace(
        config,
        server=server,
        state=state,
        models=models,
        ollama=ollama,
        openai=openai,
        logging=logging,
        safety=safety,
    )
