"""Retrieved context の prompt section wiring tests。"""

from __future__ import annotations

from iris.adapters.llm.ports import LLMRole
from iris.contracts.prompting import PromptSectionKind
from iris.contracts.retrieval import RetrievalSourceKind, RetrievedContextItem
from iris.features.chat.definition import ResponsePrompt
from iris.runtime.prompting.assembler import RuntimePromptAssembler


def test_retrieved_sources_use_external_sections_without_trusted_mixing() -> None:
    """Memory / project / transcript は source 別 external section になる。"""
    prompt = ResponsePrompt(
        system_instruction="system",
        actor_text="tea",
        retrieved_context=(
            RetrievedContextItem(
                source_id="memory-1",
                source_kind=RetrievalSourceKind.DURABLE_MEMORY,
                prompt_section_kind=PromptSectionKind.USER_MEMORY,
                text="memory tea",
                score=0.9,
                reason="memory",
            ),
            RetrievedContextItem(
                source_id="project-1",
                source_kind=RetrievalSourceKind.PROJECT_CONTEXT,
                prompt_section_kind=PromptSectionKind.PROJECT_MEMORY,
                text="project tea",
                score=0.8,
                reason="project",
            ),
            RetrievedContextItem(
                source_id="transcript-1",
                source_kind=RetrievalSourceKind.TRANSCRIPT,
                prompt_section_kind=PromptSectionKind.TASK_CONTEXT,
                text="user: transcript tea",
                score=0.7,
                reason="transcript",
            ),
        ),
    )

    result = RuntimePromptAssembler().assemble(prompt)

    assert result.messages[0].role is LLMRole.SYSTEM
    assert all(
        value not in result.messages[0].content
        for value in ("memory tea", "project tea", "transcript tea")
    )
    external = next(
        message
        for message in result.messages[1:]
        if "Untrusted external context" in message.content
    )
    assert "memory tea" in external.content
    assert "project tea" in external.content
    assert "transcript tea" in external.content
    assert any(
        report.kind is PromptSectionKind.PROJECT_MEMORY for report in result.report.section_reports
    )
