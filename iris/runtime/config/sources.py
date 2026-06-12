"""ランタイム設定向けの TOML ファイル読み込みと最上位ソースの適用。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.llm import (
    RuntimeModelsConfig,
    RuntimeOllamaConfig,
    RuntimeOpenAIConfig,
    apply_ollama_toml,
    apply_openai_toml,
)
from iris.runtime.config.llm import apply_env as apply_llm_env
from iris.runtime.config.llm import apply_toml as apply_llm_toml
from iris.runtime.config.logging import (
    RuntimeLoggingConfig,
    apply_logging_env,
    apply_logging_toml,
)
from iris.runtime.config.parsing import TomlTable, load_toml, table_or_empty, validate_toml_keys

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


def read_toml_file(path: Path) -> TomlTable:
    """ディスクから TOML 設定ファイルを読み込む。

    Args:
        path: TOML ファイルへのパス。

    Returns:
        解析済みの最上位 TOML テーブル。

    Raises:
        ConfigError: ファイルが存在しない場合。
    """
    if not path.exists():
        message = f"Runtime config file does not exist: {path}"
        raise ConfigError(message)
    with path.open("rb") as file:
        table = load_toml(file)
    validate_toml_keys(table, source=str(path))
    return table


def apply_toml(
    models: RuntimeModelsConfig,
    ollama: RuntimeOllamaConfig,
    openai: RuntimeOpenAIConfig,
    logging: RuntimeLoggingConfig,
    table: TomlTable,
) -> tuple[RuntimeModelsConfig, RuntimeOllamaConfig, RuntimeOpenAIConfig, RuntimeLoggingConfig]:
    """LLM 設定セクションに最上位 TOML テーブルを適用する。

    Args:
        models: 更新対象の models 設定。
        ollama: 更新対象の Ollama 設定。
        openai: 更新対象の OpenAI 設定。
        logging: 更新対象のロギング設定。
        table: 最上位 TOML テーブル。

    Returns:
        更新後の models / Ollama / OpenAI / logging 設定。
    """
    updated_models = apply_llm_toml(models, table_or_empty(table, "models"))
    updated_ollama = apply_ollama_toml(ollama, table_or_empty(table, "ollama"))
    updated_openai = apply_openai_toml(openai, table_or_empty(table, "openai"))
    updated_logging = apply_logging_toml(logging, table_or_empty(table, "logging"))
    return updated_models, updated_ollama, updated_openai, updated_logging


def apply_env(
    models: RuntimeModelsConfig,
    ollama: RuntimeOllamaConfig,
    openai: RuntimeOpenAIConfig,
    logging: RuntimeLoggingConfig,
    env: Mapping[str, str],
) -> tuple[RuntimeModelsConfig, RuntimeOllamaConfig, RuntimeOpenAIConfig, RuntimeLoggingConfig]:
    """LLM 設定セクションに環境変数オーバーライドを適用する。

    Args:
        models: ベースとなる models 設定。
        ollama: ベースとなる Ollama 設定。
        openai: ベースとなる OpenAI 設定。
        logging: ベースとなるロギング設定。
        env: 環境変数のマッピング。

    Returns:
        更新後の models / Ollama / OpenAI / logging 設定。
    """
    models, ollama, openai = apply_llm_env(models, ollama, openai, env)
    updated_logging = apply_logging_env(logging, env)
    return models, ollama, openai, updated_logging
