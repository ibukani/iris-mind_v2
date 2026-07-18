"""Proactive text generation port owned by the proactive feature."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from iris.contracts.proactive_talk import ProactiveGenerationResult, ProactiveTalkPrompt


class ProactiveTextGenerator(Protocol):
    """Bounded proactive prompt を text candidate へ変換する port。"""

    async def generate(self, prompt: ProactiveTalkPrompt) -> ProactiveGenerationResult:
        """Proactive text candidate を生成する。"""
        ...
