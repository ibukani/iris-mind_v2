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
from iris.cognitive.action.response import GeneratedResponse, ResponseGenerator, ResponsePrompt
from iris.runtime.config import ConfigError, IrisRuntimeConfig, RuntimeModelConfig
from iris.runtime.config.llm import LLMProvider
from iris.runtime.observability.llm import RuntimeLLMRequestObserver

if TYPE_CHECKING:
    from iris.adapters.llm.diagnostics import LLMProviderDiagnostics


class LLMResponseGenerator(ResponseGenerator):
    """LLM クライアントをバックエンドとする ResponseGenerator。"""

    def __init__(
        self,
        client: LLMClient,
        model: str = "fake-llm",
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
                LLMMessage(role=LLMRole.SYSTEM, content=prompt.system_instruction),
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
    model: str = "fake-llm",
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
        """明示的な LLM クライアントファクトリを作成する。"""
        self._known_providers = frozenset(LLMProvider)

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

        Raises:
            ConfigError: 設定されたプロバイダが未知の場合。
        """
        if model_config.provider not in self._known_providers:
            message = f"Unknown LLM provider: {model_config.provider}"
            raise ConfigError(message)
        if model_config.provider == LLMProvider.FAKE:
            return _wrap_with_observer(FakeLLMClient(model=model_config.model))
        if model_config.provider == LLMProvider.OLLAMA:
            return _wrap_with_observer(
                OllamaLLMClient(ollama_adapter_config(model_config, runtime_config)),
            )
        return _wrap_with_observer(
            OpenAILLMClient(openai_adapter_config(model_config, runtime_config)),
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

        Raises:
            ConfigError: 設定されたプロバイダが未知の場合。
        """
        if model_config.provider not in self._known_providers:
            message = f"Unknown LLM provider: {model_config.provider}"
            raise ConfigError(message)
        if model_config.provider == LLMProvider.OLLAMA:
            return ollama_adapter_config(model_config, runtime_config).model
        if model_config.provider == LLMProvider.OPENAI:
            return openai_adapter_config(model_config, runtime_config).model
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

    Raises:
        ConfigError: 未知のプロバイダ名、もしくは adapter 構築失敗時。
    """
    if model_config.provider not in frozenset(LLMProvider):
        message = f"Unknown LLM provider for diagnostics: {model_config.provider}"
        raise ConfigError(message)
    if model_config.provider == LLMProvider.FAKE:
        return None
    try:
        if model_config.provider == LLMProvider.OLLAMA:
            return OllamaDiagnostics(ollama_adapter_config(model_config, runtime_config))
        return OpenAIDiagnostics(openai_adapter_config(model_config, runtime_config))
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
    model = model_config.model
    if model == "fake-llm":
        model = OllamaConfig().model
    return OllamaConfig(
        model=model,
        base_url=runtime_config.ollama.base_url,
        timeout_seconds=runtime_config.ollama.timeout_seconds,
        temperature=model_config.temperature,
        max_output_tokens=model_config.max_output_tokens,
        keep_alive=runtime_config.ollama.keep_alive,
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
    model = model_config.model
    if model == "fake-llm":
        model = runtime_config.openai.model
    max_output_tokens = model_config.max_output_tokens
    if max_output_tokens is None:
        max_output_tokens = runtime_config.openai.max_output_tokens
    return OpenAIConfig.from_env(
        model=model,
        timeout_seconds=runtime_config.openai.timeout_seconds,
        max_output_tokens=max_output_tokens,
    )


def _wrap_with_observer(client: LLMClient) -> LLMClient:
    """Wrap an LLM client with the default request-lifecycle observer.

    The runtime's LLM client factory always emits structured request
    telemetry so operators can correlate cognitive-cycle logs with
    provider latency and error rates. The wrapper preserves the
    client type's call signature (request, response, exception
    propagation) so existing call sites are unaffected.

    Args:
        client: The bare LLM client returned by a provider constructor.

    Returns:
        The same client wrapped in :class:`ObservableLLMClient` with
        a :class:`RuntimeLLMRequestObserver`.
    """
    return ObservableLLMClient(client, RuntimeLLMRequestObserver())


def _build_user_content(prompt: ResponsePrompt) -> str:
    sections: list[str] = []
    if prompt.memory_snippets:
        snippets = "\n".join(f"- {snippet}" for snippet in prompt.memory_snippets)
        sections.append(f"Relevant memories:\n{snippets}")
    if prompt.affect_context is not None:
        sections.append(f"Affect context:\n{prompt.affect_context}")
    if prompt.relationship_context is not None:
        sections.append(f"Relationship context:\n{prompt.relationship_context}")
    if prompt.constraints:
        sections.append(f"Policy constraints: {'; '.join(prompt.constraints)}")
    if prompt.goals:
        sections.append(f"Goals: {'; '.join(prompt.goals)}")
    if not sections:
        return prompt.actor_text
    sections.append(f"Actor message:\n{prompt.actor_text}")
    return "\n\n".join(sections)
