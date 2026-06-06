"""デフォルトの IrisApp を組み立てる、コンストラクタ注入のみの構成。

サービスロケータなし、グローバルレジストリなし、認知ポリシーロジックなし。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.ollama import OllamaConfig, OllamaLLMClient
from iris.adapters.llm.openai import OpenAIConfig, OpenAILLMClient
from iris.runtime.app import IrisApp
from iris.runtime.wiring.cognitive import (
    wire_policy_affect_memory_aware_text_response_cognitive_cycle,
    wire_text_response_cognitive_cycle,
)
from iris.runtime.wiring.llm import LLMClientFactory

if TYPE_CHECKING:
    from iris.adapters.llm.ports import LLMClient
    from iris.adapters.memory.ports import MemoryStore
    from iris.runtime.config import IrisRuntimeConfig


def wire_default_app(
    llm_client: LLMClient,
    *,
    model: str = "fake-llm",
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> IrisApp:
    """標準的なテキスト応答向け認知サイクルを用いて IrisApp を組み立てる。

    Args:
        llm_client: 応答生成に利用する LLM クライアント。
        model: 応答生成に渡すモデル名。
        temperature: 応答生成に渡すサンプリング温度。
        max_tokens: 応答生成に渡す任意の出力トークン上限。

    Returns:
        完全に組み立てられた IrisApp インスタンス。
    """
    cycle = wire_text_response_cognitive_cycle(
        llm_client,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return IrisApp(cycle=cycle)


def wire_fake_app(responses: tuple[str, ...] | None = None) -> IrisApp:
    """決定論的なフェイク LLM をバックエンドとする IrisApp を組み立てる。

    Args:
        responses: FakeLLMClient に渡す任意の canned 応答文字列。

    Returns:
        完全に組み立てられた IrisApp インスタンス。
    """
    llm = FakeLLMClient(responses=responses)
    return wire_default_app(llm)


def wire_openai_app(
    config: OpenAIConfig | None = None,
    *,
    model: str = "gpt-5-mini",
) -> IrisApp:
    """OpenAI LLM クライアントをバックエンドとする IrisApp を組み立てる。

    Args:
        config: OpenAI 設定。省略時は環境から ``OPENAI_API_KEY`` を読み込む。
        model: config が省略された際に使う OpenAI モデル名。

    Returns:
        完全に組み立てられた IrisApp インスタンス。
    """
    if config is None:
        config = OpenAIConfig.from_env(model=model)
    return wire_default_app(OpenAILLMClient(config), model=config.model)


def wire_ollama_app(
    config: OllamaConfig | None = None,
    *,
    model: str = "qwen3:8b",
    base_url: str = "http://localhost:11434",
) -> IrisApp:
    """Ollama LLM クライアントをバックエンドとする IrisApp を組み立てる。

    Args:
        config: Ollama アダプタ設定。
        model: config が省略された際に使うモデル名。
        base_url: config が省略された際に使う Ollama ホスト URL。

    Returns:
        完全に組み立てられた IrisApp インスタンス。
    """
    if config is None:
        config = OllamaConfig(model=model, base_url=base_url)
    return wire_default_app(
        OllamaLLMClient(config),
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_output_tokens,
    )


def build_app_from_config(
    config: IrisRuntimeConfig,
    *,
    client_factory: LLMClientFactory | None = None,
    memory_store: MemoryStore,
) -> IrisApp:
    """ランタイム設定から IrisApp を構築する。

    ``default_chat`` モデルスロットを完全な認知サイクルへ組み込む。
    ``memory_store`` は必須引数であり、ランタイム配線は ``wire_runtime_state``
    で組み立てた永続化/編集可能なストアを明示注入する。

    Args:
        config: ランタイム設定。
        client_factory: 任意の明示的 LLM クライアントファクトリ。
        memory_store: 認知サイクルのメモリ検索に利用する ``MemoryStore``。
            ランタイム設定から組み立てた ``MutableMemoryStore`` を渡す想定。

    Returns:
        完全に組み立てられた IrisApp インスタンス。
    """
    model_config = config.models.default_chat
    factory = client_factory or LLMClientFactory()
    client = factory.create_client(model_config, config)
    model = factory.resolve_model(model_config, config)
    cycle = wire_policy_affect_memory_aware_text_response_cognitive_cycle(
        memory_store=memory_store,
        llm_client=client,
        model=model,
        temperature=model_config.temperature,
        max_tokens=model_config.max_output_tokens,
    )
    return IrisApp(cycle=cycle)
