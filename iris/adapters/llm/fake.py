"""テスト・開発用のフェイクLLMクライアント。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.llm.ports import LLMRequest, LLMResponse
from iris.contracts.llm import DEFAULT_FAKE_LLM_MODEL

if TYPE_CHECKING:
    from collections.abc import Sequence


class FakeLLMClient:
    """本番プロバイダなしでテストするための決定論的フェイクLLMクライアント。"""

    def __init__(
        self,
        responses: Sequence[str] | None = None,
        *,
        model: str = DEFAULT_FAKE_LLM_MODEL,
    ) -> None:
        """オプションの応答リストで初期化する。

        Args:
            responses: Optional sequence of predetermined response texts. When exhausted,
                the last response is reused.
            model: The model name reported in responses.
        """
        self._responses = tuple(responses) if responses is not None else None
        self._model = model
        self._requests: list[LLMRequest] = []

    @property
    def requests(self) -> tuple[LLMRequest, ...]:
        """これまでにこのクライアントに送信された全リクエストを返す。"""
        return tuple(self._requests)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """事前定義リストまたはデフォルトのフォールバックから応答を生成する。

        Returns:
            LLMResponse: 生成された応答。
        """
        self._requests.append(request)
        index = len(self._requests) - 1
        if self._responses is None:
            text = self._default_response(request)
        elif not self._responses:
            text = ""
        else:
            text = self._responses[min(index, len(self._responses) - 1)]
        return LLMResponse(text=text, model=self._model)

    @staticmethod
    def _default_response(request: LLMRequest) -> str:
        user_messages = tuple(
            message.content for message in request.messages if message.role == "user"
        )
        if not user_messages:
            return ""
        return f"fake response: {_actor_text_from_prompt(user_messages[-1])}"


def _actor_text_from_prompt(prompt: str) -> str:
    r"""Structured response promptからactor message本文を取り出す。

    セクション間は ``\n\n`` で区切られていることを前提とし、marker直後から
    次のセクション区切りまでのテキストを返す。将来 ``_build_user_content``
    でactor message以降に別セクションが追加されても影響を受けない。

    Returns:
        str: Actor message sectionがあればその本文、なければ元prompt。
    """
    marker = "Actor message:\n"
    if marker not in prompt:
        return prompt
    after = prompt.split(marker, maxsplit=1)[-1]
    idx = after.find("\n\n")
    return after[:idx] if idx != -1 else after
