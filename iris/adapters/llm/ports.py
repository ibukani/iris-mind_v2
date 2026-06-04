"""LLMアダプタ通信の型付きポート。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

LLMRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class LLMMessage:
    """LLM会話内の単一メッセージ。"""

    role: LLMRole
    content: str


@dataclass(frozen=True)
class LLMRequest:
    """LLMプロバイダへのリクエスト。"""

    model: str
    messages: tuple[LLMMessage, ...]
    temperature: float = 0.0
    max_tokens: int | None = None


@dataclass(frozen=True)
class LLMResponse:
    """LLMプロバイダからの応答。"""

    text: str
    model: str
    finish_reason: str = "stop"


class LLMClient(Protocol):
    """LLMプロバイダクライアントのプロトコル。"""

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """リクエストから応答を生成する。"""
        ...
