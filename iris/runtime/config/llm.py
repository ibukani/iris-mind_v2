"""LLM 関連のランタイム設定型とソース適用ロジック。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import (
    TomlTable,
    env_float,
    env_optional_float,
    env_optional_int,
    parse_float,
    parse_optional_float,
    parse_optional_int,
    parse_optional_string,
    parse_string,
    table_or_empty,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


class LLMProvider(StrEnum):
    """サポート対象のLLMプロバイダ。"""

    FAKE = "fake"
    OLLAMA = "ollama"
    OPENAI = "openai"


class ModelSlotName(StrEnum):
    """ランタイムのモデルスロット名。"""

    DEFAULT_CHAT = "default_chat"
    FAST_JUDGE = "fast_judge"
    REASONING = "reasoning"


_LLM_PROVIDERS: tuple[LLMProvider, ...] = (
    LLMProvider.FAKE,
    LLMProvider.OLLAMA,
    LLMProvider.OPENAI,
)
_VALID_PROVIDERS: frozenset[str] = frozenset(_LLM_PROVIDERS)
_MODEL_SLOTS: tuple[ModelSlotName, ...] = (
    ModelSlotName.DEFAULT_CHAT,
    ModelSlotName.FAST_JUDGE,
    ModelSlotName.REASONING,
)


def is_valid_provider(value: str) -> bool:
    """文字列が LLM プロバイダーとして認識可能か返す。

    Args:
        value: 確認するプロバイダー名。

    Returns:
        サポート対象プロバイダーであれば True。
    """
    return value in _VALID_PROVIDERS


def validate_provider(value: str, path: str) -> LLMProvider:
    """プロバイダー名を検証し、型付きリテラルを返す。

    Args:
        value: 検証対象のプロバイダー名。
        path: エラーメッセージに使う設定パス。

    Returns:
        検証済みプロバイダーリテラル。

    Raises:
        ConfigError: 認識できないプロバイダー名の場合。
    """
    try:
        return LLMProvider(value)
    except ValueError:
        message = f"Invalid LLM provider for {path}: {value}"
        raise ConfigError(message) from None


def env_provider(
    env: Mapping[str, str],
    key: str,
    default: LLMProvider,
    slot: ModelSlotName,
) -> LLMProvider:
    """環境変数からのプロバイダーオーバーライドを読む。

    Args:
        env: 環境変数マッピング。
        key: 読み取る変数名。
        default: 変数が無い場合に返すデフォルトプロバイダー。
        slot: エラーメッセージに使うモデルスロット。

    Returns:
        検証済みプロバイダーリテラル、またはデフォルト。
    """
    value = env.get(key)
    if value is None:
        return default
    return validate_provider(value, f"models.{slot}.provider")


@dataclass(frozen=True)
class RuntimeModelConfig:
    """1 つの名前付きモデルスロットに対するランタイム設定。"""

    provider: LLMProvider
    model: str
    temperature: float = 0.0
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class RuntimeModelsConfig:
    """すべての名前付きモデルスロットのランタイム設定。"""

    default_chat: RuntimeModelConfig
    fast_judge: RuntimeModelConfig
    reasoning: RuntimeModelConfig


@dataclass(frozen=True)
class RuntimeOllamaConfig:
    """Ollama モデルスロットで共有するランタイム設定。"""

    base_url: str = "http://localhost:11434"
    timeout_seconds: float = 120.0
    keep_alive: str | None = None


@dataclass(frozen=True)
class RuntimeOpenAIConfig:
    """OpenAI モデルスロットで共有するランタイム設定。"""

    model: str = "gpt-5-mini"
    timeout_seconds: float | None = None
    max_output_tokens: int | None = None


def apply_toml(config: RuntimeModelsConfig, models_table: TomlTable) -> RuntimeModelsConfig:
    """TOML ``[models.*]`` セクションを models config に適用する。

    Args:
        config: ベースとなる models config。
        models_table: 解析済み TOML ``[models]`` テーブル。

    Returns:
        TOML 値を反映した models config。
    """
    updated_models = config
    for slot in _MODEL_SLOTS:
        slot_config = _slot_config(updated_models, slot)
        updated_models = _replace_slot(
            updated_models,
            slot,
            _apply_model_table(
                slot_config,
                table_or_empty(models_table, slot.value),
                f"models.{slot.value}",
            ),
        )
    return updated_models


def apply_ollama_toml(
    config: RuntimeOllamaConfig,
    ollama_table: TomlTable,
) -> RuntimeOllamaConfig:
    """TOML ``[ollama]`` セクションを Ollama config に適用する。

    Args:
        config: ベースとなる Ollama config。
        ollama_table: 解析済み TOML ``[ollama]`` テーブル。

    Returns:
        TOML 値を反映した Ollama config。
    """
    base_url = config.base_url
    timeout_seconds = config.timeout_seconds
    keep_alive = config.keep_alive

    if "base_url" in ollama_table:
        base_url = parse_string(ollama_table["base_url"], "ollama.base_url")
    if "timeout_seconds" in ollama_table:
        timeout_seconds = parse_float(ollama_table["timeout_seconds"], "ollama.timeout_seconds")
    if "keep_alive" in ollama_table:
        keep_alive = parse_optional_string(ollama_table["keep_alive"], "ollama.keep_alive")
    return RuntimeOllamaConfig(
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        keep_alive=keep_alive,
    )


def apply_openai_toml(
    config: RuntimeOpenAIConfig,
    openai_table: TomlTable,
) -> RuntimeOpenAIConfig:
    """TOML ``[openai]`` セクションを OpenAI config に適用する。

    Args:
        config: ベースとなる OpenAI config。
        openai_table: 解析済み TOML ``[openai]`` テーブル。

    Returns:
        TOML 値を反映した OpenAI config。
    """
    model = config.model
    timeout_seconds = config.timeout_seconds
    max_output_tokens = config.max_output_tokens

    if "model" in openai_table:
        model = parse_string(openai_table["model"], "openai.model")
    if "timeout_seconds" in openai_table:
        timeout_seconds = parse_optional_float(
            openai_table["timeout_seconds"],
            "openai.timeout_seconds",
        )
    if "max_output_tokens" in openai_table:
        max_output_tokens = parse_optional_int(
            openai_table["max_output_tokens"],
            "openai.max_output_tokens",
        )
    return RuntimeOpenAIConfig(
        model=model,
        timeout_seconds=timeout_seconds,
        max_output_tokens=max_output_tokens,
    )


def apply_env(
    config: RuntimeModelsConfig,
    ollama: RuntimeOllamaConfig,
    openai: RuntimeOpenAIConfig,
    env: Mapping[str, str],
) -> tuple[RuntimeModelsConfig, RuntimeOllamaConfig, RuntimeOpenAIConfig]:
    """環境変数オーバーライドを LLM 設定セクションへ適用する。

    Args:
        config: ベースとなる models config。
        ollama: ベースとなる Ollama config。
        openai: ベースとなる OpenAI config。
        env: 環境変数マッピング。

    Returns:
        更新後の models / Ollama / OpenAI config。
    """
    updated_models = config
    for slot in _MODEL_SLOTS:
        slot_config = _slot_config(updated_models, slot)
        updated_models = _replace_slot(
            updated_models,
            slot,
            _apply_model_env(slot_config, slot, env),
        )
    return (
        updated_models,
        _apply_ollama_env(ollama, env),
        _apply_openai_env(openai, env),
    )


def _apply_model_table(
    config: RuntimeModelConfig,
    table: TomlTable,
    path: str,
) -> RuntimeModelConfig:
    """単一モデルスロットの TOML テーブルを model config に適用する。

    Args:
        config: ベースとなる model config。
        table: モデルスロットに対応する解析済み TOML テーブル。
        path: エラーメッセージに使う設定パス。

    Returns:
        TOML 値を反映した model config。
    """
    provider = config.provider
    model = config.model
    temperature = config.temperature
    max_output_tokens = config.max_output_tokens

    if "provider" in table:
        provider = validate_provider(
            parse_string(table["provider"], f"{path}.provider"),
            path,
        )
    if "model" in table:
        model = parse_string(table["model"], f"{path}.model")
    if "temperature" in table:
        temperature = parse_float(table["temperature"], f"{path}.temperature")
    if "max_output_tokens" in table:
        max_output_tokens = parse_optional_int(
            table["max_output_tokens"],
            f"{path}.max_output_tokens",
        )
    return RuntimeModelConfig(
        provider=provider,
        model=model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def _apply_model_env(
    config: RuntimeModelConfig,
    slot: ModelSlotName,
    env: Mapping[str, str],
) -> RuntimeModelConfig:
    """1 つのモデルスロットへ環境変数オーバーライドを適用する。

    Args:
        config: ベースとなる model config。
        slot: 環境変数プレフィックスを組み立てるためのモデルスロット名。
        env: 環境変数マッピング。

    Returns:
        環境変数値を反映した model config。
    """
    prefix = f"IRIS_{slot.upper()}_"
    provider = env_provider(env, f"{prefix}PROVIDER", config.provider, slot)
    model = env.get(f"{prefix}MODEL", config.model)
    temperature = env_float(env, f"{prefix}TEMPERATURE", config.temperature)
    max_output_tokens = env_optional_int(
        env,
        f"{prefix}MAX_OUTPUT_TOKENS",
        config.max_output_tokens,
    )
    return RuntimeModelConfig(
        provider=provider,
        model=model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def _apply_ollama_env(
    config: RuntimeOllamaConfig,
    env: Mapping[str, str],
) -> RuntimeOllamaConfig:
    """環境変数オーバーライドを Ollama config へ適用する。

    Args:
        config: ベースとなる Ollama config。
        env: 環境変数マッピング。

    Returns:
        環境変数値を反映した Ollama config。
    """
    return RuntimeOllamaConfig(
        base_url=env.get("IRIS_OLLAMA_HOST", config.base_url),
        timeout_seconds=env_float(
            env,
            "IRIS_OLLAMA_TIMEOUT_SECONDS",
            config.timeout_seconds,
        ),
        keep_alive=env.get("IRIS_OLLAMA_KEEP_ALIVE", config.keep_alive),
    )


def _apply_openai_env(
    config: RuntimeOpenAIConfig,
    env: Mapping[str, str],
) -> RuntimeOpenAIConfig:
    """環境変数オーバーライドを OpenAI config へ適用する。

    Args:
        config: ベースとなる OpenAI config。
        env: 環境変数マッピング。

    Returns:
        環境変数値を反映した OpenAI config。
    """
    return RuntimeOpenAIConfig(
        model=env.get("IRIS_OPENAI_MODEL", config.model),
        timeout_seconds=env_optional_float(
            env,
            "IRIS_OPENAI_TIMEOUT_SECONDS",
            config.timeout_seconds,
        ),
        max_output_tokens=env_optional_int(
            env,
            "IRIS_OPENAI_MAX_OUTPUT_TOKENS",
            config.max_output_tokens,
        ),
    )


def _replace_slot(
    models: RuntimeModelsConfig,
    slot: ModelSlotName,
    config: RuntimeModelConfig,
) -> RuntimeModelsConfig:
    """指定スロットを差し替えた ``models`` のコピーを返す。

    Args:
        models: ベースとなる models config。
        slot: 差し替えるスロット名。
        config: スロットに格納する新しい model config。

    Returns:
        スロットを差し替えた models config。
    """
    return replace(models, **{slot: config})


def _slot_config(
    models: RuntimeModelsConfig,
    slot: ModelSlotName,
) -> RuntimeModelConfig:
    """指定モデルスロットの現在の config を返す。

    Args:
        models: 読み取り元の models config。
        slot: 読み取るスロット名。

    Returns:
        指定スロットに格納された model config。
    """
    if slot == ModelSlotName.DEFAULT_CHAT:
        return models.default_chat
    if slot == ModelSlotName.FAST_JUDGE:
        return models.fast_judge
    return models.reasoning
