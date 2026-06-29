"""LLM 関連のランタイム設定型とソース適用ロジック。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING

from iris.contracts.llm import DEFAULT_FAKE_LLM_MODEL, DEFAULT_OPENAI_MODEL
from iris.runtime.config.errors import ConfigError
from iris.runtime.config.model_slots import model_slot_specs
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
    from collections.abc import Callable, Mapping


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


def model_slot_names() -> tuple[ModelSlotName, ...]:
    """ランタイムが扱うモデルスロット名の正規順序を返す。

    Returns:
        ``default_chat`` / ``fast_judge`` / ``reasoning`` の順序。
    """
    return tuple(ModelSlotName(spec.name) for spec in model_slot_specs())


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


def default_runtime_models_config() -> RuntimeModelsConfig:
    """ランタイムの既定モデル設定を返す。

    Returns:
        fake プロバイダを使う既定の models 設定。
    """
    return RuntimeModelsConfig(
        default_chat=_default_runtime_model_config(512),
        fast_judge=_default_runtime_model_config(128),
        reasoning=_default_runtime_model_config(1024),
    )


type RuntimeOllamaThink = bool | str | None
_VALID_OLLAMA_THINK_LEVELS: frozenset[str] = frozenset({"low", "medium", "high"})


@dataclass(frozen=True)
class RuntimeOllamaConfig:
    """Ollama モデルスロットで共有するランタイム設定。"""

    base_url: str = "http://localhost:11434"
    timeout_seconds: float = 120.0
    keep_alive: str | None = None
    think: RuntimeOllamaThink = False


@dataclass(frozen=True)
class RuntimeOpenAIConfig:
    """OpenAI モデルスロットで共有するランタイム設定。"""

    model: str = DEFAULT_OPENAI_MODEL
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
    return _update_models_for_slots(
        config,
        lambda slot, slot_config: _RuntimeModelConfigPatch.from_table(
            table_or_empty(models_table, slot.value),
            f"models.{slot.value}",
        ).apply(slot_config),
    )


def _default_runtime_model_config(max_output_tokens: int) -> RuntimeModelConfig:
    """Fake LLM の既定モデル設定を作る。

    Args:
        max_output_tokens: モデルスロットごとの既定出力上限。

    Returns:
        fake プロバイダの既定 model config。
    """
    return RuntimeModelConfig(
        provider=LLMProvider.FAKE,
        model=DEFAULT_FAKE_LLM_MODEL,
        max_output_tokens=max_output_tokens,
    )


def parse_ollama_think(value: object, path: str) -> RuntimeOllamaThink:
    """Parse Ollama think setting from TOML-compatible values.

    Args:
        value: The value to parse.
        path: Configuration path for error messages.

    Returns:
        The parsed think setting.

    Raises:
        ConfigError: If the value is invalid.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value in _VALID_OLLAMA_THINK_LEVELS:
            return value
        lowered = value.strip().lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        if lowered in {"none", "null"}:
            return None
    allowed = "true, false, low, medium, high, null"
    message = f"Invalid {path}: {value}. Allowed values: {allowed}"
    raise ConfigError(message)


def env_ollama_think(
    env: Mapping[str, str],
    key: str,
    default: RuntimeOllamaThink,
) -> RuntimeOllamaThink:
    """環境変数からの Ollama think オーバーライドを読む。

    Args:
        env: The environment dictionary.
        key: The environment variable key.
        default: The default think setting to return if key is unset.

    Returns:
        The parsed think setting, or the default if not provided.
    """
    value = env.get(key)
    if value is None:
        return default
    return parse_ollama_think(value, key)


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
    return _RuntimeOllamaConfigPatch.from_table(ollama_table).apply(config)


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
    return _RuntimeOpenAIConfigPatch.from_table(openai_table).apply(config)


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
    updated_models = _update_models_for_slots(
        config,
        lambda slot, slot_config: _RuntimeModelConfigPatch.from_env(slot, env).apply(
            slot_config,
        ),
    )
    return (
        updated_models,
        _RuntimeOllamaConfigPatch.from_env(env).apply(ollama),
        _RuntimeOpenAIConfigPatch.from_env(env).apply(openai),
    )


def _update_models_for_slots(
    config: RuntimeModelsConfig,
    apply_slot: Callable[[ModelSlotName, RuntimeModelConfig], RuntimeModelConfig],
) -> RuntimeModelsConfig:
    """全モデルスロットへ順に変換を適用する。

    Args:
        config: ベースとなる models config。
        apply_slot: 各スロットの入力 config を受けて更新後 config を返す関数。

    Returns:
        全スロットへ変換を適用した models config。
    """
    updated_models = config
    for slot in model_slot_names():
        slot_config = runtime_model_config_for_slot(updated_models, slot)
        updated_models = replace_runtime_model_config_for_slot(
            updated_models,
            slot,
            apply_slot(slot, slot_config),
        )
    return updated_models


def replace_runtime_model_config_for_slot(
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
    match slot:
        case ModelSlotName.DEFAULT_CHAT:
            return replace(models, default_chat=config)
        case ModelSlotName.FAST_JUDGE:
            return replace(models, fast_judge=config)
        case ModelSlotName.REASONING:
            return replace(models, reasoning=config)


def runtime_model_config_for_slot(
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
    match slot:
        case ModelSlotName.DEFAULT_CHAT:
            return models.default_chat
        case ModelSlotName.FAST_JUDGE:
            return models.fast_judge
        case ModelSlotName.REASONING:
            return models.reasoning


@dataclass(frozen=True)
class _RuntimeModelConfigPatch:
    """単一モデルスロットの optional 更新値を束ねる。"""

    provider: LLMProvider | None = None
    model: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    max_output_tokens_set: bool = False

    @classmethod
    def from_table(cls, table: TomlTable, path: str) -> _RuntimeModelConfigPatch:
        """TOML テーブルから patch を組み立てる。

        Returns:
            組み立てた model patch。
        """
        return cls(
            provider=(
                validate_provider(parse_string(table["provider"], f"{path}.provider"), path)
                if "provider" in table
                else None
            ),
            model=(parse_string(table["model"], f"{path}.model") if "model" in table else None),
            temperature=(
                parse_float(table["temperature"], f"{path}.temperature")
                if "temperature" in table
                else None
            ),
            max_output_tokens=(
                parse_optional_int(table["max_output_tokens"], f"{path}.max_output_tokens")
                if "max_output_tokens" in table
                else None
            ),
            max_output_tokens_set="max_output_tokens" in table,
        )

    @classmethod
    def from_env(
        cls,
        slot: ModelSlotName,
        env: Mapping[str, str],
    ) -> _RuntimeModelConfigPatch:
        """環境変数から patch を組み立てる。

        Returns:
            組み立てた model patch。
        """
        prefix = f"IRIS_{slot.upper()}_"
        return cls(
            provider=(
                validate_provider(
                    parse_string(env[f"{prefix}PROVIDER"], f"models.{slot}.provider"),
                    f"models.{slot}.provider",
                )
                if f"{prefix}PROVIDER" in env
                else None
            ),
            model=env.get(f"{prefix}MODEL", None),
            temperature=(
                env_float(env, f"{prefix}TEMPERATURE", 0.0)
                if f"{prefix}TEMPERATURE" in env
                else None
            ),
            max_output_tokens=(
                env_optional_int(env, f"{prefix}MAX_OUTPUT_TOKENS", None)
                if f"{prefix}MAX_OUTPUT_TOKENS" in env
                else None
            ),
            max_output_tokens_set=f"{prefix}MAX_OUTPUT_TOKENS" in env,
        )

    def apply(self, config: RuntimeModelConfig) -> RuntimeModelConfig:
        """Model 設定へ patch を適用する。

        Returns:
            更新後の model config。
        """
        return RuntimeModelConfig(
            provider=config.provider if self.provider is None else self.provider,
            model=config.model if self.model is None else self.model,
            temperature=config.temperature if self.temperature is None else self.temperature,
            max_output_tokens=(
                config.max_output_tokens
                if not self.max_output_tokens_set
                else self.max_output_tokens
            ),
        )


@dataclass(frozen=True)
class _RuntimeOllamaConfigPatch:
    """Ollama の optional 更新値を束ねる。"""

    base_url: str | None = None
    timeout_seconds: float | None = None
    keep_alive: str | None = None
    keep_alive_set: bool = False
    think: RuntimeOllamaThink = False
    think_set: bool = False

    @classmethod
    def from_table(cls, table: TomlTable) -> _RuntimeOllamaConfigPatch:
        """TOML テーブルから patch を組み立てる。

        Returns:
            組み立てた ollama patch。
        """
        return cls(
            base_url=(
                parse_string(table["base_url"], "ollama.base_url") if "base_url" in table else None
            ),
            timeout_seconds=(
                parse_float(table["timeout_seconds"], "ollama.timeout_seconds")
                if "timeout_seconds" in table
                else None
            ),
            keep_alive=(
                parse_optional_string(table["keep_alive"], "ollama.keep_alive")
                if "keep_alive" in table
                else None
            ),
            keep_alive_set="keep_alive" in table,
            think=(
                parse_ollama_think(table["think"], "ollama.think") if "think" in table else False
            ),
            think_set="think" in table,
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> _RuntimeOllamaConfigPatch:
        """環境変数から patch を組み立てる。

        Returns:
            組み立てた ollama patch。
        """
        return cls(
            base_url=env.get("IRIS_OLLAMA_HOST", None),
            timeout_seconds=(
                env_float(env, "IRIS_OLLAMA_TIMEOUT_SECONDS", 0.0)
                if "IRIS_OLLAMA_TIMEOUT_SECONDS" in env
                else None
            ),
            keep_alive=env.get("IRIS_OLLAMA_KEEP_ALIVE", None),
            keep_alive_set="IRIS_OLLAMA_KEEP_ALIVE" in env,
            think=(
                env_ollama_think(env, "IRIS_OLLAMA_THINK", None)
                if "IRIS_OLLAMA_THINK" in env
                else False
            ),
            think_set="IRIS_OLLAMA_THINK" in env,
        )

    def apply(self, config: RuntimeOllamaConfig) -> RuntimeOllamaConfig:
        """Ollama 設定へ patch を適用する。

        Returns:
            更新後の Ollama config。
        """
        return RuntimeOllamaConfig(
            base_url=config.base_url if self.base_url is None else self.base_url,
            timeout_seconds=(
                config.timeout_seconds if self.timeout_seconds is None else self.timeout_seconds
            ),
            keep_alive=config.keep_alive if not self.keep_alive_set else self.keep_alive,
            think=config.think if not self.think_set else self.think,
        )


@dataclass(frozen=True)
class _RuntimeOpenAIConfigPatch:
    """OpenAI の optional 更新値を束ねる。"""

    model: str | None = None
    timeout_seconds: float | None = None
    timeout_seconds_set: bool = False
    max_output_tokens: int | None = None
    max_output_tokens_set: bool = False

    @classmethod
    def from_table(cls, table: TomlTable) -> _RuntimeOpenAIConfigPatch:
        """TOML テーブルから patch を組み立てる。

        Returns:
            組み立てた openai patch。
        """
        return cls(
            model=(parse_string(table["model"], "openai.model") if "model" in table else None),
            timeout_seconds=(
                parse_optional_float(table["timeout_seconds"], "openai.timeout_seconds")
                if "timeout_seconds" in table
                else None
            ),
            timeout_seconds_set="timeout_seconds" in table,
            max_output_tokens=(
                parse_optional_int(table["max_output_tokens"], "openai.max_output_tokens")
                if "max_output_tokens" in table
                else None
            ),
            max_output_tokens_set="max_output_tokens" in table,
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> _RuntimeOpenAIConfigPatch:
        """環境変数から patch を組み立てる。

        Returns:
            組み立てた openai patch。
        """
        return cls(
            model=env.get("IRIS_OPENAI_MODEL", None),
            timeout_seconds=(
                env_optional_float(env, "IRIS_OPENAI_TIMEOUT_SECONDS", 0.0)
                if "IRIS_OPENAI_TIMEOUT_SECONDS" in env
                else None
            ),
            timeout_seconds_set="IRIS_OPENAI_TIMEOUT_SECONDS" in env,
            max_output_tokens=(
                env_optional_int(env, "IRIS_OPENAI_MAX_OUTPUT_TOKENS", None)
                if "IRIS_OPENAI_MAX_OUTPUT_TOKENS" in env
                else None
            ),
            max_output_tokens_set="IRIS_OPENAI_MAX_OUTPUT_TOKENS" in env,
        )

    def apply(self, config: RuntimeOpenAIConfig) -> RuntimeOpenAIConfig:
        """OpenAI 設定へ patch を適用する。

        Returns:
            更新後の OpenAI config。
        """
        return RuntimeOpenAIConfig(
            model=config.model if self.model is None else self.model,
            timeout_seconds=(
                config.timeout_seconds if not self.timeout_seconds_set else self.timeout_seconds
            ),
            max_output_tokens=(
                config.max_output_tokens
                if not self.max_output_tokens_set
                else self.max_output_tokens
            ),
        )
