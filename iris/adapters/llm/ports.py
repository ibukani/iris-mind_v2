"""LLMアダプタ通信の型付きポート。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class LLMRole(StrEnum):
    """LLMメッセージのロール。"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


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
    temperature: float | None = None
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
