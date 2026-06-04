"""OpenAI LLMプロバイダアダプタ。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import contextlib
from dataclasses import dataclass
import os
from typing import Any, Protocol, cast

from iris.adapters.llm.ports import LLMMessage, LLMRequest, LLMResponse

_openai: Any = None
with contextlib.suppress(ImportError):
    import openai as _openai


@dataclass(frozen=True)
class OpenAIConfig:
    """OpenAI LLMクライアントの設定。"""

    model: str
    api_key: str | None = None
    timeout_seconds: float | None = None
    max_output_tokens: int | None = None

    @classmethod
    def from_env(
        cls,
        *,
        model: str = "gpt-5-mini",
        api_key_name: str = "OPENAI_API_KEY",
        timeout_seconds: float | None = None,
        max_output_tokens: int | None = None,
    ) -> OpenAIConfig:
        """環境変数から設定を生成する。

        Returns:
            OpenAIConfig: 環境変数から生成された設定。
        """
        return cls(
            model=model,
            api_key=os.environ.get(api_key_name),
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
        )


class OpenAIAdapterError(RuntimeError):
    """OpenAIアダプタ障害時に送出されるエラー。"""


class OpenAIResponsesClient(Protocol):
    """OpenAI Responses APIクライアントのプロトコル。"""

    @property
    def responses(self) -> OpenAIResponsesResource:
        """responsesリソースハンドルを返す。"""
        ...


class OpenAIResponsesResource(Protocol):
    """OpenAI Responses APIリソースのプロトコル。"""

    async def create(self, **kwargs: object) -> object:
        """指定されたパラメータで応答を生成する。"""


_ERR_OPENAI_NOT_INSTALLED = "OpenAI SDK is not installed. Install the 'openai' package."
_ERR_API_KEY_REQUIRED = "OpenAI API key is required when no OpenAI client is injected."


class OpenAILLMClient:
    """OpenAI Responses APIをバックエンドとするLLMクライアント。"""

    def __init__(self, config: OpenAIConfig, client: OpenAIResponsesClient | None = None) -> None:
        """設定とオプションの注入クライアントで初期化する。

        Args:
            config: The OpenAI configuration.
            client: An optional injected client instance. When omitted, the client is
                constructed from the config's API key.

        Raises:
            OpenAIAdapterError: openai パッケージがインストールされていない場合。
        """
        self._config = config
        if client is not None:
            self._client = client
            return

        if _openai is None:
            raise OpenAIAdapterError(_ERR_OPENAI_NOT_INSTALLED)
        if config.api_key is None:
            raise OpenAIAdapterError(_ERR_API_KEY_REQUIRED)

        self._client = cast(
            "OpenAIResponsesClient",
            _openai.AsyncOpenAI(api_key=config.api_key, timeout=config.timeout_seconds),
        )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """リクエストからLLM応答を生成する。

        Returns:
            LLMResponse: 生成された応答テキストとメタデータ。
        """
        response = await self._client.responses.create(**self._to_provider_request(request))
        return LLMResponse(
            text=_extract_output_text(response),
            model=_extract_response_model(response, request.model),
            finish_reason=_extract_finish_reason(response),
        )

    def _to_provider_request(self, request: LLMRequest) -> dict[str, object]:
        max_output_tokens = request.max_tokens or self._config.max_output_tokens
        provider_request: dict[str, object] = {
            "model": request.model or self._config.model,
            "input": tuple(_to_provider_message(message) for message in request.messages),
            "temperature": request.temperature,
        }
        if max_output_tokens is not None:
            provider_request["max_output_tokens"] = max_output_tokens
        return provider_request


def _to_provider_message(message: LLMMessage) -> dict[str, str]:
    return {
        "role": message.role,
        "content": message.content,
    }


def _extract_output_text(response: object) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str):
        return output_text

    chunks: list[str] = []
    for output_item in _iter_response_output(response):
        for content_item in _iter_content(output_item):
            text = _get_text(content_item)
            if text:
                chunks.append(text)
    return "".join(chunks)


def _iter_response_output(response: object) -> tuple[object, ...]:
    output = _get_value(response, "output")
    if isinstance(output, list | tuple):
        items: Iterable[object] = cast("Iterable[object]", output)
        return tuple(items)
    return ()


def _iter_content(output_item: object) -> tuple[object, ...]:
    content = _get_value(output_item, "content")
    if isinstance(content, list | tuple):
        items: Iterable[object] = cast("Iterable[object]", content)
        return tuple(items)
    return ()


def _get_text(content_item: object) -> str | None:
    text = _get_value(content_item, "text")
    if isinstance(text, str):
        return text
    return None


def _get_value(item: object, name: str) -> object:
    if isinstance(item, Mapping):
        mapping: Mapping[str, object] = cast("Mapping[str, object]", item)
        return mapping.get(name, None)
    return getattr(item, name, None)


def _extract_response_model(response: object, fallback: str) -> str:
    model = getattr(response, "model", None)
    if isinstance(model, str):
        return model
    return fallback


def _extract_finish_reason(response: object) -> str:
    status = getattr(response, "status", None)
    if isinstance(status, str):
        return status
    return "stop"
