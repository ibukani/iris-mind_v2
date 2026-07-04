"""Runtime prompt budget config tests."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from iris.contracts.prompting import PromptOverflowBehavior, PromptProfileName, PromptSectionKind
from iris.runtime.config import ConfigError, default_runtime_config, load_runtime_config
from iris.runtime.config.prompt_budget import (
    RuntimePromptBudgetConfig,
    RuntimePromptProfileBudget,
    RuntimePromptSectionBudget,
    memory_top_k_for_profile,
    project_context_top_k_for_profile,
    validate_prompt_budget_config,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_default_prompt_budget_profiles_match_issue_91_policy() -> None:
    """既定設定は local profile と proactive short profile を持つ。"""
    config = default_runtime_config().prompt_budget

    assert config.enabled
    assert config.chat_profile is PromptProfileName.LOCAL_BALANCED
    assert config.proactive_profile is PromptProfileName.PROACTIVE_SHORT
    assert config.local_low.total_max_chars < config.local_balanced.total_max_chars
    assert config.local_balanced.total_max_chars < config.local_quality.total_max_chars
    assert config.proactive_short.total_max_chars < config.local_balanced.total_max_chars
    assert config.local_balanced.user_memory.max_items == 5
    assert memory_top_k_for_profile(config, PromptProfileName.LOCAL_BALANCED) == 5
    assert project_context_top_k_for_profile(config, PromptProfileName.LOCAL_BALANCED) == 4


def test_runtime_prompt_profile_budget_exports_section_mapping_contract() -> None:
    """Runtime profile budget は section kind 付き contract として公開できる。"""
    runtime_budget = RuntimePromptBudgetConfig().local_balanced

    contract = runtime_budget.to_contract(PromptProfileName.LOCAL_BALANCED)

    assert contract.name is PromptProfileName.LOCAL_BALANCED
    assert contract.total_max_chars == runtime_budget.total_max_chars
    assert (
        contract.section_budget(PromptSectionKind.USER_MEMORY).max_items
        == runtime_budget.user_memory.max_items
    )


def test_prompt_budget_toml_override_is_loaded(tmp_path: Path) -> None:
    """TOML で profile と section budget を上書きできる。"""
    config_path = tmp_path / "runtime.toml"
    config_path.write_text(
        """
[config]
version = 2

[prompt_budget]
chat_profile = "local_low"

[advanced.prompt_budget.local_low]
total_max_chars = 4096

[advanced.prompt_budget.local_low.user_memory]
max_chars = 123
max_items = 2
priority = 42
overflow_behavior = "truncate_items"
""".strip(),
        encoding="utf-8",
    )

    config = load_runtime_config(config_path, env={}).prompt_budget

    assert config.chat_profile is PromptProfileName.LOCAL_LOW
    assert config.local_low.total_max_chars == 4096
    assert config.local_low.user_memory.max_chars == 123
    assert config.local_low.user_memory.max_items == 2
    assert config.local_low.user_memory.priority == 42
    assert config.local_low.user_memory.overflow_behavior is PromptOverflowBehavior.TRUNCATE_ITEMS


def test_prompt_budget_rejects_invalid_profile_and_behavior(tmp_path: Path) -> None:
    """不正な profile 名と overflow behavior は config load 時に拒否される。"""
    invalid_profile = tmp_path / "invalid-profile.toml"
    invalid_profile.write_text(
        """
[config]
version = 2

[prompt_budget]
chat_profile = "huge"
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match=r"Invalid prompt_budget\.chat_profile"):
        load_runtime_config(invalid_profile, env={})

    invalid_behavior = tmp_path / "invalid-behavior.toml"
    invalid_behavior.write_text(
        """
[config]
version = 2

[advanced.prompt_budget.local_low.user_memory]
overflow_behavior = "random"
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match=r"Invalid prompt_budget\.local_low\.user_memory"):
        load_runtime_config(invalid_behavior, env={})


def test_prompt_budget_rejects_proactive_profile_longer_than_chat() -> None:
    """Proactive short profile は通常 chat より短く保つ。"""
    config = RuntimePromptBudgetConfig(
        proactive_short=RuntimePromptProfileBudget(
            total_max_chars=10000,
            system=_section(1),
            persona=_section(1),
            safety_constraints=_section(1),
            recent_conversation=_section(1),
            user_memory=_section(1),
            project_memory=_section(1),
            relationship_signal=_section(1),
            internal_state=_section(1),
            interaction_policy=_section(1),
            task_context=_section(1),
            user_input=_section(1),
        )
    )

    with pytest.raises(ConfigError, match="proactive_short"):
        validate_prompt_budget_config(config)


def test_prompt_budget_rejects_required_sections_larger_than_total() -> None:
    """Required section caps は profile total を超えない。"""
    config = RuntimePromptBudgetConfig()
    config = replace(
        config,
        local_low=replace(
            config.local_low,
            total_max_chars=100,
            system=RuntimePromptSectionBudget(
                max_chars=80,
                max_items=1,
                priority=100,
                overflow_behavior=PromptOverflowBehavior.REQUIRED,
            ),
            user_input=RuntimePromptSectionBudget(
                max_chars=80,
                max_items=1,
                priority=100,
                overflow_behavior=PromptOverflowBehavior.REQUIRED,
            ),
        ),
    )

    with pytest.raises(ConfigError, match="required section max_chars"):
        validate_prompt_budget_config(config)


def test_prompt_budget_rejects_required_sections_that_exceed_total_with_separators() -> None:
    """Required trusted sections は最終 system message の separator 分も含める。"""
    config = RuntimePromptBudgetConfig()
    config = replace(
        config,
        local_low=replace(
            config.local_low,
            total_max_chars=101,
            system=RuntimePromptSectionBudget(
                max_chars=50,
                max_items=1,
                priority=100,
                overflow_behavior=PromptOverflowBehavior.REQUIRED,
            ),
            safety_constraints=RuntimePromptSectionBudget(
                max_chars=50,
                max_items=2,
                priority=99,
                overflow_behavior=PromptOverflowBehavior.REQUIRED,
            ),
            user_input=RuntimePromptSectionBudget(
                max_chars=1,
                max_items=1,
                priority=100,
                overflow_behavior=PromptOverflowBehavior.REQUIRED,
            ),
        ),
    )

    with pytest.raises(ConfigError, match="including trusted separators"):
        validate_prompt_budget_config(config)


def test_prompt_budget_rejects_required_internal_or_external_sections() -> None:
    """Required は最終 cap を壊さない trusted/user sections に限定する。"""
    config = RuntimePromptBudgetConfig()
    config = replace(
        config,
        local_low=replace(
            config.local_low,
            internal_state=RuntimePromptSectionBudget(
                max_chars=80,
                max_items=1,
                priority=100,
                overflow_behavior=PromptOverflowBehavior.REQUIRED,
            ),
        ),
    )

    with pytest.raises(ConfigError, match="required section must be one of"):
        validate_prompt_budget_config(config)


def test_prompt_budget_rejects_required_section_with_zero_items() -> None:
    """Required section は item section 化されても omit されない item cap を持つ。"""
    config = RuntimePromptBudgetConfig()
    config = replace(
        config,
        local_low=replace(
            config.local_low,
            safety_constraints=RuntimePromptSectionBudget(
                max_chars=80,
                max_items=0,
                priority=100,
                overflow_behavior=PromptOverflowBehavior.REQUIRED,
            ),
        ),
    )

    with pytest.raises(ConfigError, match="required section must have max_items"):
        validate_prompt_budget_config(config)


def _section(max_chars: int) -> RuntimePromptSectionBudget:
    return RuntimePromptSectionBudget(
        max_chars=max_chars,
        max_items=1,
        priority=1,
        overflow_behavior=PromptOverflowBehavior.TRUNCATE,
    )
