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

from iris.runtime.config.llm import (
    LLMProvider,
    RuntimeModelConfig,
    RuntimeModelsConfig,
    RuntimeOllamaConfig,
    RuntimeOpenAIConfig,
    validate_provider,
)
from iris.runtime.config.logging import RuntimeLoggingConfig
from iris.runtime.config.parsing import table_or_empty
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


@dataclass(frozen=True)
class IrisRuntimeConfig:
    """アプリケーションワイヤリングが利用するランタイム設定。"""

    server: RuntimeServerConfig
    state: RuntimeStateConfig
    models: RuntimeModelsConfig
    ollama: RuntimeOllamaConfig
    openai: RuntimeOpenAIConfig
    logging: RuntimeLoggingConfig


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
        server=RuntimeServerConfig(),
        state=RuntimeStateConfig(),
        models=RuntimeModelsConfig(
            default_chat=RuntimeModelConfig(provider="fake", model="fake-llm"),
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
    )


def load_runtime_config(
    config_path: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    overrides: RuntimeConfigOverrides | None = None,
) -> IrisRuntimeConfig:
    """デフォルト・TOML・環境変数・オーバーライドからランタイム設定を読み込む。

    Args:
        config_path: 任意の明示的 TOML ファイルパス。
        env: 環境変数のマッピング。デフォルトは ``os.environ``。
        overrides: 任意のオーバーライド値。

    Returns:
        検証済みのランタイム設定。
    """
    config = default_runtime_config()
    if config_path is not None:
        config = _apply_toml(config, read_toml_file(Path(config_path)))
    config = _apply_env(config, os.environ if env is None else env)
    if overrides is not None:
        config = apply_runtime_overrides(config, overrides)

    config = replace(config, server=validate_server_config(config.server))
    return replace(config, state=validate_state_config(config.state))


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


def _apply_toml(config: IrisRuntimeConfig, table: TomlTable) -> IrisRuntimeConfig:
    """最上位 TOML テーブルをランタイム設定全体に適用する。

    Args:
        config: ベースとなるランタイム設定。
        table: 解析済みの最上位 TOML テーブル。

    Returns:
        TOML 値を反映したランタイム設定。
    """
    server = apply_server_toml(config.server, table_or_empty(table, "server"))
    state = apply_state_toml(config.state, table_or_empty(table, "state"))

    models, ollama, openai, logging = apply_toml(
        config.models,
        config.ollama,
        config.openai,
        config.logging,
        table,
    )
    return replace(
        config,
        server=server,
        state=state,
        models=models,
        ollama=ollama,
        openai=openai,
        logging=logging,
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
    server = apply_server_env(config.server, env)
    state = apply_state_env(config.state, env)

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
    )
