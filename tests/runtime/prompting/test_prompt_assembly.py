"""Runtime prompt assembly tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from iris.adapters.llm.ports import LLMRole
from iris.contracts.conversation import ConversationRecord, ConversationRole
from iris.contracts.prompting import PromptOverflowBehavior, PromptSectionKind
from iris.core.ids import ObservationId, SessionId
from iris.features.chat.definition import ResponsePrompt
from iris.runtime.config.prompt_budget import RuntimePromptBudgetConfig, RuntimePromptSectionBudget
from iris.runtime.persona import PersonaProfileLoader, SystemPromptBuilder
from iris.runtime.prompting.assembler import RuntimePromptAssembler

if TYPE_CHECKING:
    from pathlib import Path


def test_prompt_assembler_separates_trusted_internal_external_and_user() -> None:
    """trusted/system, internal, external, user input を role message 上でも分離する。"""
    prompt = ResponsePrompt(
        system_instruction="sys",
        actor_text="こんにちは",
        memory_snippets=("memory item",),
        affect_context="affect",
        relationship_context="relationship",
        constraints=("policy",),
        goals=("goal",),
    )

    result = RuntimePromptAssembler(RuntimePromptBudgetConfig()).assemble(prompt)

    assert result.messages[0].role is LLMRole.SYSTEM
    assert result.messages[-1].role is LLMRole.USER
    assert result.messages[-1].content == "こんにちは"
    system = result.messages[0].content
    assert "System instruction" in system
    assert "Runtime response guardrails" in system
    assert "Internal runtime context" not in system
    assert "Affect context" not in system
    assert "External context" not in system
    assert "Relevant memories" not in system
    assert "こんにちは" not in system

    internal_context = result.messages[1]
    external_context = result.messages[2]
    assert internal_context.role is LLMRole.USER
    assert "Internal runtime context" in internal_context.content
    assert "Affect context" in internal_context.content
    assert "Relationship signal" in internal_context.content
    assert "Policy constraints" in internal_context.content
    assert external_context.role is LLMRole.USER
    assert "Untrusted external context" in external_context.content
    assert "Relevant memories" in external_context.content
    assert result.report.profile.value == "local_balanced"


def test_prompt_assembler_budgets_persona_separately_before_safety() -> None:
    """Persona は trusted section として budget/report に入り、safety と混ざらない。"""
    loaded = PersonaProfileLoader().load_default()
    assembler = RuntimePromptAssembler(
        RuntimePromptBudgetConfig(),
        system_prompt_builder=SystemPromptBuilder(loaded.profile()),
    )

    result = assembler.assemble(
        ResponsePrompt(
            system_instruction="system",
            actor_text="user text",
            memory_snippets=("untrusted memory",),
            constraints=("account-specific policy",),
        )
    )

    reports = {report.kind: report for report in result.report.section_reports}
    assert reports[PromptSectionKind.PERSONA].output_chars > 0
    assert result.report.persona_profile_version == "1"
    assert result.report.persona_fallback_used is False
    system = result.messages[0].content
    assert system.index("Global Iris persona") < system.index("Runtime response guardrails")
    assert "untrusted memory" not in system
    assert "account-specific policy" not in system


def test_prompt_assembler_reports_persona_fallback_and_truncation(tmp_path: Path) -> None:
    """Persona fallback と section truncation を assembly report に残す。"""
    loaded = PersonaProfileLoader().load(tmp_path / "missing.toml")
    base = RuntimePromptBudgetConfig()
    config = replace(
        base,
        local_balanced=replace(
            base.local_balanced,
            persona=RuntimePromptSectionBudget(
                max_chars=80,
                max_items=1,
                priority=95,
                overflow_behavior=PromptOverflowBehavior.TRUNCATE,
            ),
        ),
    )
    assembler = RuntimePromptAssembler(
        config,
        system_prompt_builder=SystemPromptBuilder(
            loaded.profile(),
            used_fallback=loaded.used_fallback,
        ),
    )

    result = assembler.assemble(ResponsePrompt(system_instruction="system", actor_text="hello"))

    persona_report = next(
        report
        for report in result.report.section_reports
        if report.kind is PromptSectionKind.PERSONA
    )
    assert result.report.persona_profile_version == "fallback-v1"
    assert result.report.persona_fallback_used is True
    assert persona_report.output_chars <= 80
    assert persona_report.truncated_chars > 0


def test_prompt_assembler_uses_proactive_short_profile_when_selected() -> None:
    """Proactive profile を明示指定できる。"""
    config = RuntimePromptBudgetConfig()
    result = RuntimePromptAssembler(config, profile=config.proactive_profile).assemble(
        ResponsePrompt(system_instruction="sys", actor_text="tick")
    )

    assert result.report.profile is config.proactive_profile
    assert result.report.total_max_chars == config.proactive_short.total_max_chars


def test_prompt_assembler_applies_char_budget_to_actual_history_messages() -> None:
    """recent_conversation の char budget は実際の LLM messages にも反映される。"""
    config = RuntimePromptBudgetConfig()
    config = replace(
        config,
        local_balanced=replace(
            config.local_balanced,
            recent_conversation=RuntimePromptSectionBudget(
                max_chars=45,
                max_items=10,
                priority=70,
                overflow_behavior=PromptOverflowBehavior.TRUNCATE_ITEMS,
            ),
        ),
    )
    long_history = "latest-" + "x" * 80
    prompt = ResponsePrompt(
        system_instruction="sys",
        actor_text="current",
        conversation_history=(
            ConversationRecord(
                role=ConversationRole.USER,
                content="old",
                occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
                observation_id=ObservationId("obs-old"),
                session_id=SessionId("session"),
            ),
            ConversationRecord(
                role=ConversationRole.ASSISTANT,
                content=long_history,
                occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
                observation_id=ObservationId("obs-latest"),
                session_id=SessionId("session"),
            ),
        ),
    )

    result = RuntimePromptAssembler(config).assemble(prompt)

    history_message = result.messages[1]
    history_report = next(
        report
        for report in result.report.section_reports
        if report.kind is PromptSectionKind.RECENT_CONVERSATION
    )
    assert history_report.output_chars <= 45
    assert history_report.truncated_chars > 0
    assert history_message.role is LLMRole.ASSISTANT
    assert history_message.content.startswith("latest-")
    assert history_message.content != long_history
    assert "x" * 80 not in history_message.content


def test_prompt_assembler_applies_budget_to_latest_user_message() -> None:
    """Latest user message も user_input section として budget accounting される。"""
    config = RuntimePromptBudgetConfig()
    config = replace(
        config,
        local_balanced=replace(
            config.local_balanced,
            user_input=RuntimePromptSectionBudget(
                max_chars=28,
                max_items=1,
                priority=100,
                overflow_behavior=PromptOverflowBehavior.REQUIRED,
            ),
        ),
    )
    actor_text = "hello-" + "y" * 80

    result = RuntimePromptAssembler(config).assemble(
        ResponsePrompt(system_instruction="sys", actor_text=actor_text)
    )

    user_report = next(
        report
        for report in result.report.section_reports
        if report.kind is PromptSectionKind.USER_INPUT
    )
    assert user_report.output_chars <= 28
    assert user_report.truncated_chars > 0
    assert result.messages[-1].role is LLMRole.USER
    assert result.messages[-1].content.startswith("hello")
    assert result.messages[-1].content != actor_text
    assert "y" * 80 not in result.messages[-1].content


def test_prompt_assembler_accounts_relationship_signal_separately() -> None:
    """relationship_context は internal_state ではなく relationship_signal section になる。"""
    prompt = ResponsePrompt(
        system_instruction="sys",
        actor_text="hi",
        affect_context="affect",
        relationship_context="relationship",
    )

    result = RuntimePromptAssembler(RuntimePromptBudgetConfig()).assemble(prompt)

    reports = {report.kind for report in result.report.section_reports}
    assert PromptSectionKind.INTERNAL_STATE in reports
    assert PromptSectionKind.RELATIONSHIP_SIGNAL in reports
    relationship_report = next(
        report
        for report in result.report.section_reports
        if report.kind is PromptSectionKind.RELATIONSHIP_SIGNAL
    )
    assert relationship_report.output_items == 1
    assert "Relationship signal" in result.messages[1].content


def test_prompt_assembler_total_budget_truncates_actual_history_messages() -> None:
    """Total budget overflow 後も recent_conversation の実 message は cap を迂回しない。"""
    base_config = RuntimePromptBudgetConfig()
    local_balanced = replace(
        base_config.local_balanced,
        total_max_chars=260,
        system=RuntimePromptSectionBudget(
            max_chars=120,
            max_items=1,
            priority=100,
            overflow_behavior=PromptOverflowBehavior.REQUIRED,
        ),
        safety_constraints=RuntimePromptSectionBudget(
            max_chars=80,
            max_items=2,
            priority=98,
            overflow_behavior=PromptOverflowBehavior.TRUNCATE_ITEMS,
        ),
        recent_conversation=RuntimePromptSectionBudget(
            max_chars=400,
            max_items=3,
            priority=10,
            overflow_behavior=PromptOverflowBehavior.TRUNCATE_ITEMS,
        ),
        user_input=RuntimePromptSectionBudget(
            max_chars=80,
            max_items=1,
            priority=100,
            overflow_behavior=PromptOverflowBehavior.REQUIRED,
        ),
    )
    config = replace(base_config, local_balanced=local_balanced)
    long_history = "history-" + "z" * 300

    result = RuntimePromptAssembler(config).assemble(
        ResponsePrompt(
            system_instruction="sys",
            actor_text="current",
            conversation_history=(
                ConversationRecord(
                    role=ConversationRole.USER,
                    content=long_history,
                    occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
                    observation_id=ObservationId("obs-history"),
                    session_id=SessionId("session"),
                ),
            ),
        )
    )

    history_report = next(
        report
        for report in result.report.section_reports
        if report.kind is PromptSectionKind.RECENT_CONVERSATION
    )
    history_messages = [message for message in result.messages if message.role is LLMRole.USER]
    assert result.report.total_chars <= config.local_balanced.total_max_chars
    assert history_report.output_chars <= config.local_balanced.recent_conversation.max_chars
    assert history_report.truncated_chars > 0
    assert history_report.output_items == 1
    assert history_messages[0].content.startswith("history-")
    assert history_messages[0].content != long_history
    assert "z" * 300 not in history_messages[0].content


def test_prompt_assembler_reports_and_enforces_final_message_total_chars() -> None:
    """Group label 等を含む最終 LLM message content も total budget 内に収める。"""
    base_config = RuntimePromptBudgetConfig()
    local_balanced = replace(
        base_config.local_balanced,
        total_max_chars=200,
        system=RuntimePromptSectionBudget(
            max_chars=50,
            max_items=1,
            priority=100,
            overflow_behavior=PromptOverflowBehavior.REQUIRED,
        ),
        safety_constraints=RuntimePromptSectionBudget(
            max_chars=50,
            max_items=2,
            priority=98,
            overflow_behavior=PromptOverflowBehavior.TRUNCATE_ITEMS,
        ),
        user_memory=RuntimePromptSectionBudget(
            max_chars=80,
            max_items=1,
            priority=55,
            overflow_behavior=PromptOverflowBehavior.TRUNCATE_ITEMS,
        ),
        internal_state=RuntimePromptSectionBudget(
            max_chars=80,
            max_items=1,
            priority=60,
            overflow_behavior=PromptOverflowBehavior.TRUNCATE_ITEMS,
        ),
        user_input=RuntimePromptSectionBudget(
            max_chars=50,
            max_items=1,
            priority=100,
            overflow_behavior=PromptOverflowBehavior.REQUIRED,
        ),
    )
    config = replace(base_config, local_balanced=local_balanced)

    result = RuntimePromptAssembler(config).assemble(
        ResponsePrompt(
            system_instruction="s" * 40,
            actor_text="u" * 40,
            affect_context="a" * 30,
            memory_snippets=("m" * 30,),
        )
    )

    actual_total_chars = sum(len(message.content) for message in result.messages)
    assert actual_total_chars <= config.local_balanced.total_max_chars
    assert result.report.total_chars == actual_total_chars
    assert result.report.total_max_chars == config.local_balanced.total_max_chars


def test_prompt_assembler_tiny_history_budget_preserves_role_prefix_when_kept() -> None:
    """recent_conversation を truncate しても role prefix を壊さず message 化する。"""
    config = RuntimePromptBudgetConfig()
    config = replace(
        config,
        local_balanced=replace(
            config.local_balanced,
            recent_conversation=RuntimePromptSectionBudget(
                max_chars=30,
                max_items=1,
                priority=70,
                overflow_behavior=PromptOverflowBehavior.TRUNCATE_ITEMS,
            ),
        ),
    )

    result = RuntimePromptAssembler(config).assemble(
        ResponsePrompt(
            system_instruction="sys",
            actor_text="current",
            conversation_history=(
                ConversationRecord(
                    role=ConversationRole.USER,
                    content="abcdefghi",
                    occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
                    observation_id=ObservationId("obs-history-tiny"),
                    session_id=SessionId("session"),
                ),
            ),
        )
    )

    history_report = next(
        report
        for report in result.report.section_reports
        if report.kind is PromptSectionKind.RECENT_CONVERSATION
    )
    history_messages = result.messages[1:-1]
    assert history_report.output_items == 1
    assert len(history_messages) == 1
    assert history_messages[0].role is LLMRole.USER
    assert history_messages[0].content == "…"


def test_prompt_assembler_too_tiny_history_budget_reports_omitted_message() -> None:
    """Role prefix も保持できない recent_conversation item は report と実 message で落とす。"""
    config = RuntimePromptBudgetConfig()
    config = replace(
        config,
        local_balanced=replace(
            config.local_balanced,
            recent_conversation=RuntimePromptSectionBudget(
                max_chars=20,
                max_items=1,
                priority=70,
                overflow_behavior=PromptOverflowBehavior.TRUNCATE_ITEMS,
            ),
        ),
    )

    result = RuntimePromptAssembler(config).assemble(
        ResponsePrompt(
            system_instruction="sys",
            actor_text="current",
            conversation_history=(
                ConversationRecord(
                    role=ConversationRole.USER,
                    content="abcdefghi",
                    occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
                    observation_id=ObservationId("obs-history-omitted"),
                    session_id=SessionId("session"),
                ),
            ),
        )
    )

    history_report = next(
        report
        for report in result.report.section_reports
        if report.kind is PromptSectionKind.RECENT_CONVERSATION
    )
    assert history_report.omitted
    assert history_report.output_items == 0
    assert result.messages[1:-1] == ()


def test_prompt_assembler_tiny_user_input_budget_keeps_user_text_not_title() -> None:
    """User input の char budget は section title ではなく実 user text に適用する。"""
    config = RuntimePromptBudgetConfig()
    config = replace(
        config,
        local_balanced=replace(
            config.local_balanced,
            user_input=RuntimePromptSectionBudget(
                max_chars=5,
                max_items=1,
                priority=100,
                overflow_behavior=PromptOverflowBehavior.REQUIRED,
            ),
        ),
    )

    result = RuntimePromptAssembler(config).assemble(
        ResponsePrompt(system_instruction="sys", actor_text="abcdefghi")
    )

    assert result.messages[-1].role is LLMRole.USER
    assert result.messages[-1].content == "abcd…"
    assert "Latest" not in result.messages[-1].content
