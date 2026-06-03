from __future__ import annotations

from collections.abc import Sequence

from iris.adapters.llm.ports import LLMRequest, LLMResponse


class FakeLLMClient:
    def __init__(
        self,
        responses: Sequence[str] | None = None,
        *,
        model: str = "fake-llm",
    ) -> None:
        self._responses = tuple(responses) if responses is not None else None
        self._model = model
        self._requests: list[LLMRequest] = []

    @property
    def requests(self) -> tuple[LLMRequest, ...]:
        return tuple(self._requests)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self._requests.append(request)
        index = len(self._requests) - 1
        if self._responses is None:
            text = self._default_response(request)
        elif not self._responses:
            text = ""
        else:
            text = self._responses[min(index, len(self._responses) - 1)]
        return LLMResponse(text=text, model=self._model)

    def _default_response(self, request: LLMRequest) -> str:
        user_messages = tuple(message.content for message in request.messages if message.role == "user")
        if not user_messages:
            return ""
        return f"fake response: {user_messages[-1]}"
