from __future__ import annotations

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.openai import OpenAIConfig, OpenAILLMClient
from iris.adapters.llm.ports import LLMClient, LLMMessage, LLMRequest
from iris.cognitive.action.response import GeneratedResponse, ResponseGenerator, ResponsePrompt


class LLMResponseGenerator(ResponseGenerator):
    def __init__(self, client: LLMClient, *, model: str = "fake-llm") -> None:
        self._client = client
        self._model = model

    async def generate_response(self, prompt: ResponsePrompt) -> GeneratedResponse:
        request = LLMRequest(
            model=self._model,
            messages=(
                LLMMessage(role="system", content=prompt.system_instruction),
                LLMMessage(role="user", content=_build_user_content(prompt)),
            ),
            temperature=0.0,
        )
        response = await self._client.generate(request)
        return GeneratedResponse(text=response.text, model=response.model)


def wire_fake_llm_client(responses: tuple[str, ...] | None = None) -> FakeLLMClient:
    return FakeLLMClient(responses=responses)


def wire_response_generator(client: LLMClient | None = None) -> LLMResponseGenerator:
    if client is None:
        client = wire_fake_llm_client()
    return LLMResponseGenerator(client)


def wire_openai_llm_client(config: OpenAIConfig) -> LLMClient:
    return OpenAILLMClient(config)


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
        return prompt.user_text
    sections.append(f"User message:\n{prompt.user_text}")
    return "\n\n".join(sections)
