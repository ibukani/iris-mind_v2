from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

LLMRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class LLMMessage:
    role: LLMRole
    content: str


@dataclass(frozen=True)
class LLMRequest:
    model: str
    messages: tuple[LLMMessage, ...]
    temperature: float = 0.0
    max_tokens: int | None = None


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    finish_reason: str = "stop"


class LLMClient(Protocol):
    async def generate(self, request: LLMRequest) -> LLMResponse: ...
