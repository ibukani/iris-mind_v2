"""LLM クライアントのワイヤリングと応答生成器の実装。"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.observability import ObservableLLMClient
from iris.adapters.llm.ollama import OllamaConfig, OllamaLLMClient
from iris.adapters.llm.ollama_diagnostics import OllamaDiagnostics
from iris.adapters.llm.openai import OpenAIAdapterError, OpenAIConfig, OpenAILLMClient
from iris.adapters.llm.openai_diagnostics import OpenAIDiagnostics
from iris.adapters.llm.ports import LLMClient, LLMMessage, LLMRequest, LLMRole
from iris.contracts.conversation import ConversationRole
from iris.contracts.llm import DEFAULT_FAKE_LLM_MODEL
from iris.features.chat.definition import GeneratedResponse, ResponseGenerator, ResponsePrompt
from iris.runtime.config import ConfigError, IrisRuntimeConfig, RuntimeModelConfig
from iris.runtime.config.llm import LLMProvider
from iris.runtime.observability.llm import RuntimeLLMRequestObserver

if TYPE_CHECKING:
    from iris.adapters.llm.diagnostics import LLMProviderDiagnostics
    from iris.contracts.conversation import ConversationRecord
    from iris.runtime.observability.ports import RuntimeLatencyBudget


_KNOWN_LLM_PROVIDERS: frozenset[LLMProvider] = frozenset(LLMProvider)


class LLMResponseGenerator(ResponseGenerator):
    """LLM クライアントをバックエンドとする ResponseGenerator。"""

    def __init__(
        self,
        client: LLMClient,
        model: str = DEFAULT_FAKE_LLM_MODEL,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> None:
        """LLM バックエンドの応答生成器を作成する。

        Args:
            client: LLM クライアント。
            model: LLM プロバイダに渡すモデル名。
            temperature: LLM プロバイダに渡すサンプリング温度。
            max_tokens: LLM プロバイダに渡す任意の出力トークン上限。
        """
        self._client = client
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    @override
    async def generate_response(self, prompt: ResponsePrompt) -> GeneratedResponse:
        """プロンプトに対する応答テキストを生成する。

        Args:
            prompt: 応答生成プロンプト。

        Returns:
            生成された応答テキストとモデルメタデータ。
        """
        request = LLMRequest(
            model=self._model,
            messages=(
                LLMMessage(role=LLMRole.SYSTEM, content=_build_system_content(prompt)),
                *tuple(_conversation_message(record) for record in prompt.conversation_history),
                LLMMessage(role=LLMRole.USER, content=_build_user_content(prompt)),
            ),
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        response = await self._client.generate(request)
        return GeneratedResponse(text=response.text, model=response.model)


def wire_fake_llm_client(responses: tuple[str, ...] | None = None) -> FakeLLMClient:
    """決定論的なフェイク LLM クライアントを組み立てる。

    Args:
        responses: 任意の canned 応答文字列。

    Returns:
        FakeLLMClient インスタンス。
    """
    return FakeLLMClient(responses=responses)


def wire_response_generator(
    client: LLMClient | None = None,
    *,
    model: str = DEFAULT_FAKE_LLM_MODEL,
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> LLMResponseGenerator:
    """応答生成器を組み立てる。

    Args:
        client: 任意の LLM クライアント。省略時はフェイククライアントを使用。
        model: LLM プロバイダに渡すモデル名。
        temperature: LLM プロバイダに渡すサンプリング温度。
        max_tokens: LLM プロバイダに渡す任意の出力トークン上限。

    Returns:
        LLMResponseGenerator インスタンス。
    """
    if client is None:
        client = wire_fake_llm_client()
    return LLMResponseGenerator(
        client,
        model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def wire_openai_llm_client(config: OpenAIConfig) -> LLMClient:
    """OpenAI LLM クライアントを組み立てる。

    Args:
        config: OpenAI 設定。

    Returns:
        OpenAILLMClient インスタンス。
    """
    return OpenAILLMClient(config)


def wire_ollama_llm_client(config: OllamaConfig) -> LLMClient:
    """Ollama LLM クライアントを組み立てる。

    Args:
        config: Ollama アダプタ設定。

    Returns:
        OllamaLLMClient インスタンス。
    """
    return OllamaLLMClient(config)


class LLMClientFactory:
    """プロバイダ固有の LLM クライアントを組み立てる明示的なランタイムファクトリ。"""

    def __init__(self) -> None:
        """既知の LLM provider 集合を共有参照する。"""
        self._known_providers = _KNOWN_LLM_PROVIDERS

    def create_client(
        self,
        model_config: RuntimeModelConfig,
        runtime_config: IrisRuntimeConfig,
    ) -> LLMClient:
        """ランタイムモデルスロット向けの LLM クライアントを生成する。

        Args:
            model_config: モデルスロット設定。
            runtime_config: ランタイム設定全体。

        Returns:
            プロバイダ中立な LLM クライアント。
        """
        provider = _require_known_provider(
            model_config.provider,
            "Unknown LLM provider",
            self._known_providers,
        )
        client = _build_llm_client(provider, model_config, runtime_config)
        return _wrap_with_observer(
            client,
            latency_budget=runtime_config.observability.latency_budget,
        )

    def resolve_model(
        self,
        model_config: RuntimeModelConfig,
        runtime_config: IrisRuntimeConfig,
    ) -> str:
        """プロバイダ中立な LLMRequest で送るモデル名を解決する。

        Args:
            model_config: モデルスロット設定。
            runtime_config: ランタイム設定全体。

        Returns:
            応答生成に渡すモデル名。
        """
        provider = _require_known_provider(
            model_config.provider,
            "Unknown LLM provider",
            self._known_providers,
        )
        if provider == LLMProvider.OLLAMA:
            return _resolve_ollama_model(model_config.model)
        if provider == LLMProvider.OPENAI:
            return _resolve_openai_model(model_config.model, runtime_config)
        return model_config.model


def build_provider_diagnostics(
    model_config: RuntimeModelConfig,
    runtime_config: IrisRuntimeConfig,
) -> LLMProviderDiagnostics | None:
    """モデルスロット設定からプロバイダ診断を組み立てる。

    ``provider == "fake"`` の場合は ``None`` を返し、診断対象外であることを示す。
    openai プロバイダは SDK 不在 / API key 不在時に ``OpenAIAdapterError`` を
    送出し、この関数では ``ConfigError`` に翻訳して再送出する。
    呼び出し側は ``ConfigError`` のみ catch すればよく、 concrete adapter
    シンボルへの依存なしで構築失敗を扱える。

    Args:
        model_config: モデルスロット設定。
        runtime_config: ランタイム設定全体。

    Returns:
        組み立てた診断インスタンス。 fake プロバイダなら ``None``。

    """
    provider = _require_known_provider(
        model_config.provider,
        "Unknown LLM provider for diagnostics",
    )
    return _build_provider_diagnostics(provider, model_config, runtime_config)


def _require_known_provider(
    provider: LLMProvider,
    message_prefix: str,
    known_providers: frozenset[LLMProvider] = _KNOWN_LLM_PROVIDERS,
) -> LLMProvider:
    """既知のプロバイダか検証する。

    Args:
        provider: 検証対象のプロバイダ。
        message_prefix: エラーメッセージの先頭。
        known_providers: 許可する provider の集合。

    Returns:
        検証済みプロバイダ。

    Raises:
        ConfigError: provider が未対応の場合。
    """
    if provider not in known_providers:
        message = f"{message_prefix}: {provider}"
        raise ConfigError(message)
    return provider


def _build_llm_client(
    provider: LLMProvider,
    model_config: RuntimeModelConfig,
    runtime_config: IrisRuntimeConfig,
) -> LLMClient:
    """Provider ごとの LLM client を組み立てる。

    Returns:
        構成済みの LLM client。
    """
    match provider:
        case LLMProvider.FAKE:
            return FakeLLMClient(model=model_config.model)
        case LLMProvider.OLLAMA:
            return wire_ollama_llm_client(
                ollama_adapter_config(model_config, runtime_config),
            )
        case LLMProvider.OPENAI:
            return wire_openai_llm_client(
                openai_adapter_config(model_config, runtime_config),
            )


def _build_provider_diagnostics(
    provider: LLMProvider,
    model_config: RuntimeModelConfig,
    runtime_config: IrisRuntimeConfig,
) -> LLMProviderDiagnostics | None:
    """Provider ごとの診断を組み立てる。

    Returns:
        構成済みの provider diagnostics。 fake provider なら None。

    Raises:
        ConfigError: openai diagnostics 構築失敗時。
    """
    try:
        match provider:
            case LLMProvider.FAKE:
                return None
            case LLMProvider.OLLAMA:
                return OllamaDiagnostics(
                    ollama_adapter_config(model_config, runtime_config),
                )
            case LLMProvider.OPENAI:
                return OpenAIDiagnostics(
                    openai_adapter_config(model_config, runtime_config),
                )
    except OpenAIAdapterError as exc:
        message = f"Failed to build openai provider diagnostics: {exc}"
        raise ConfigError(message) from exc


def ollama_adapter_config(
    model_config: RuntimeModelConfig,
    runtime_config: IrisRuntimeConfig,
) -> OllamaConfig:
    """RuntimeModelConfig + IrisRuntimeConfig を Ollama アダプタ用 OllamaConfig に変換する。

    Args:
        model_config: モデルスロット設定。
        runtime_config: ランタイム設定全体。

    Returns:
        ``OllamaLLMClient`` / ``OllamaDiagnostics`` が受け取る ``OllamaConfig``。
    """
    model = _resolve_ollama_model(model_config.model)
    return OllamaConfig(
        model=model,
        base_url=runtime_config.ollama.base_url,
        timeout_seconds=runtime_config.ollama.timeout_seconds,
        temperature=model_config.temperature,
        max_output_tokens=model_config.max_output_tokens,
        keep_alive=runtime_config.ollama.keep_alive,
        think=runtime_config.ollama.think,
    )


def openai_adapter_config(
    model_config: RuntimeModelConfig,
    runtime_config: IrisRuntimeConfig,
) -> OpenAIConfig:
    """RuntimeModelConfig + IrisRuntimeConfig を OpenAI アダプタ用 OpenAIConfig に変換する。

    Args:
        model_config: モデルスロット設定。
        runtime_config: ランタイム設定全体。

    Returns:
        ``OpenAILLMClient`` / ``OpenAIDiagnostics`` が受け取る ``OpenAIConfig``。
        API key は環境変数 ``OPENAI_API_KEY`` から解決される。
    """
    model = _resolve_openai_model(model_config.model, runtime_config)
    max_output_tokens = model_config.max_output_tokens
    if max_output_tokens is None:
        max_output_tokens = runtime_config.openai.max_output_tokens
    return OpenAIConfig.from_env(
        model=model,
        timeout_seconds=runtime_config.openai.timeout_seconds,
        max_output_tokens=max_output_tokens,
    )


def _wrap_with_observer(
    client: LLMClient,
    *,
    latency_budget: RuntimeLatencyBudget,
) -> LLMClient:
    """LLM client を既定の request lifecycle observer で包む。

    Runtime の LLM client factory は、cognitive-cycle log と provider latency /
    error rate を対応付けられるように、構造化された request telemetry を常に
    出力する。wrapper は request / response / exception propagation の呼び出し
    契約を保つため、既存の呼び出し側には影響しない。

    Args:
        client: provider constructor が返した素の LLM client。
        latency_budget: Runtime LLM generation latency budget。

    Returns:
        :class:`RuntimeLLMRequestObserver` を持つ :class:`ObservableLLMClient` で
        包んだ LLM client。
    """
    return ObservableLLMClient(
        client,
        RuntimeLLMRequestObserver(latency_budget=latency_budget),
    )


def _is_fake_llm_model(model: str) -> bool:
    """Fake LLM sentinel model か判定する。

    Returns:
        fake センチネルなら True。
    """
    return model == DEFAULT_FAKE_LLM_MODEL


def _resolve_ollama_model(model: str) -> str:
    """Ollama 用の実際のモデル名を解決する。

    Returns:
        実際に Ollama へ渡すモデル名。
    """
    if _is_fake_llm_model(model):
        return OllamaConfig().model
    return model


def _resolve_openai_model(model: str, runtime_config: IrisRuntimeConfig) -> str:
    """OpenAI 用の実際のモデル名を解決する。

    Returns:
        実際に OpenAI へ渡すモデル名。
    """
    if _is_fake_llm_model(model):
        return runtime_config.openai.model
    return model


_INTERNAL_CONTEXT_GUARDRAIL = (
    "Use the internal context only to shape tone and response selection. "
    "Never mention affect scores, relationship scores, trust, familiarity, "
    "policy constraints, memory retrieval metadata, or the response-generation process. "
    "Respond directly as Iris."
)

_LANGUAGE_GUARDRAIL = (
    "Respond in the same natural language as the user's latest message. "
    "If the latest user message is Japanese, respond in natural Japanese only. "
    "Do not mix Chinese unless the user explicitly asks for Chinese."
)


def _build_system_content(prompt: ResponsePrompt) -> str:
    sections = [
        prompt.system_instruction,
        _INTERNAL_CONTEXT_GUARDRAIL,
        _LANGUAGE_GUARDRAIL,
    ]
    internal_context = _build_internal_context(prompt)
    if internal_context is not None:
        sections.append(f"Internal context:\n{internal_context}")
    return "\n\n".join(section for section in sections if section.strip())


def _build_internal_context(prompt: ResponsePrompt) -> str | None:
    sections: list[str] = []
    if prompt.conversation_summary is not None:
        sections.append(_build_context_section("Conversation summary", prompt.conversation_summary))
    if prompt.memory_snippets:
        snippets = "\n".join(f"- {snippet}" for snippet in prompt.memory_snippets)
        sections.append(_build_context_section("Relevant memories", snippets))
    if prompt.affect_context is not None:
        sections.append(_build_context_section("Affect context", prompt.affect_context))
    if prompt.relationship_context is not None:
        sections.append(_build_context_section("Relationship context", prompt.relationship_context))
    if prompt.constraints:
        sections.append(_build_context_section("Policy constraints", "; ".join(prompt.constraints)))
    if prompt.goals:
        sections.append(_build_context_section("Goals", "; ".join(prompt.goals)))
    if not sections:
        return None
    return "\n\n".join(sections)


def _build_context_section(title: str, body: str) -> str:
    return f"{title}:\n{body}"


def _build_user_content(prompt: ResponsePrompt) -> str:
    return prompt.actor_text


def _conversation_message(record: ConversationRecord) -> LLMMessage:
    """短期会話recordをLLM messageへ変換する。

    Returns:
        roleを保持したLLM message。
    """
    role = LLMRole.USER if record.role is ConversationRole.USER else LLMRole.ASSISTANT
    return LLMMessage(role=role, content=record.content)
