"""Prompt section budget と context compression policy のランタイム設定。"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from iris.contracts.prompting import (
    PromptOverflowBehavior,
    PromptProfileName,
    PromptSectionBudget,
    PromptSectionKind,
)
from iris.runtime.config.errors import ConfigError

if TYPE_CHECKING:
    from collections.abc import Iterable

type TomlScalar = str | int | float | bool | None
type TomlValue = TomlScalar | TomlArray | TomlTable
type TomlArray = list[TomlValue]
type TomlTable = dict[str, TomlValue]

_PROMPT_SECTION_KINDS: tuple[PromptSectionKind, ...] = tuple(PromptSectionKind)
_PROMPT_PROFILE_NAMES: tuple[PromptProfileName, ...] = tuple(PromptProfileName)
_PROMPT_OVERFLOW_BEHAVIORS: tuple[PromptOverflowBehavior, ...] = tuple(PromptOverflowBehavior)
_REQUIRED_PROMPT_SECTION_KINDS: tuple[PromptSectionKind, ...] = (
    PromptSectionKind.SYSTEM,
    PromptSectionKind.SAFETY_CONSTRAINTS,
    PromptSectionKind.USER_INPUT,
)


def _default_local_low_profile() -> RuntimePromptProfileBudget:
    return _local_low_profile()


def _default_local_balanced_profile() -> RuntimePromptProfileBudget:
    return _local_balanced_profile()


def _default_local_quality_profile() -> RuntimePromptProfileBudget:
    return _local_quality_profile()


def _default_proactive_short_profile() -> RuntimePromptProfileBudget:
    return _proactive_short_profile()


@dataclass(frozen=True)
class RuntimePromptSectionBudget:
    """単一 prompt section の runtime budget 設定。"""

    max_chars: int
    max_items: int
    priority: int
    overflow_behavior: PromptOverflowBehavior

    def to_contract(self) -> PromptSectionBudget:
        """共有契約の `PromptSectionBudget` へ変換する。

        Returns:
            共有境界で利用する prompt section budget 契約。
        """
        return PromptSectionBudget(
            max_chars=self.max_chars,
            max_items=self.max_items,
            priority=self.priority,
            overflow_behavior=self.overflow_behavior,
        )


@dataclass(frozen=True)
class RuntimePromptProfileBudget:
    """Profile ごとの prompt budget 設定。"""

    total_max_chars: int
    system: RuntimePromptSectionBudget
    persona: RuntimePromptSectionBudget
    safety_constraints: RuntimePromptSectionBudget
    recent_conversation: RuntimePromptSectionBudget
    user_memory: RuntimePromptSectionBudget
    project_memory: RuntimePromptSectionBudget
    relationship_signal: RuntimePromptSectionBudget
    internal_state: RuntimePromptSectionBudget
    interaction_policy: RuntimePromptSectionBudget
    task_context: RuntimePromptSectionBudget
    user_input: RuntimePromptSectionBudget

    def section_budget(self, kind: PromptSectionKind) -> RuntimePromptSectionBudget:
        """Section kind に対応する budget を返す。

        Args:
            kind: 取得対象の prompt section kind。

        Returns:
            対応する runtime prompt section budget。
        """
        budgets = {
            PromptSectionKind.SYSTEM: self.system,
            PromptSectionKind.PERSONA: self.persona,
            PromptSectionKind.SAFETY_CONSTRAINTS: self.safety_constraints,
            PromptSectionKind.RECENT_CONVERSATION: self.recent_conversation,
            PromptSectionKind.USER_MEMORY: self.user_memory,
            PromptSectionKind.PROJECT_MEMORY: self.project_memory,
            PromptSectionKind.RELATIONSHIP_SIGNAL: self.relationship_signal,
            PromptSectionKind.INTERNAL_STATE: self.internal_state,
            PromptSectionKind.INTERACTION_POLICY: self.interaction_policy,
            PromptSectionKind.TASK_CONTEXT: self.task_context,
            PromptSectionKind.USER_INPUT: self.user_input,
        }
        return budgets[kind]


@dataclass(frozen=True)
class RuntimePromptBudgetConfig:
    """Runtime 全体の prompt budget 設定。"""

    enabled: bool = True
    chat_profile: PromptProfileName = PromptProfileName.LOCAL_BALANCED
    proactive_profile: PromptProfileName = PromptProfileName.PROACTIVE_SHORT
    local_low: RuntimePromptProfileBudget = field(default_factory=_default_local_low_profile)
    local_balanced: RuntimePromptProfileBudget = field(
        default_factory=_default_local_balanced_profile
    )
    local_quality: RuntimePromptProfileBudget = field(
        default_factory=_default_local_quality_profile
    )
    proactive_short: RuntimePromptProfileBudget = field(
        default_factory=_default_proactive_short_profile
    )

    def profile_budget(self, profile: PromptProfileName) -> RuntimePromptProfileBudget:
        """Profile 名に対応する budget を返す。

        Args:
            profile: 取得対象の prompt profile 名。

        Returns:
            対応する runtime prompt profile budget。
        """
        budgets = {
            PromptProfileName.LOCAL_LOW: self.local_low,
            PromptProfileName.LOCAL_BALANCED: self.local_balanced,
            PromptProfileName.LOCAL_QUALITY: self.local_quality,
            PromptProfileName.PROACTIVE_SHORT: self.proactive_short,
        }
        return budgets[profile]


def default_prompt_budget_config() -> RuntimePromptBudgetConfig:
    """既定の prompt budget 設定を返す。

    Returns:
        既定値で構築した runtime prompt budget config。
    """
    return RuntimePromptBudgetConfig()


def profile_budget_for_call_site(
    config: RuntimePromptBudgetConfig,
    *,
    proactive: bool = False,
) -> RuntimePromptProfileBudget:
    """Chat / proactive の呼び出し場所に応じた profile budget を返す。

    Args:
        config: Runtime prompt budget config。
        proactive: proactive generation 用 profile を使うかどうか。

    Returns:
        呼び出し場所に対応する prompt profile budget。
    """
    profile = config.proactive_profile if proactive else config.chat_profile
    return config.profile_budget(profile)


def section_budget_for_profile(
    config: RuntimePromptBudgetConfig,
    profile: PromptProfileName,
    section: PromptSectionKind,
) -> RuntimePromptSectionBudget:
    """#94 retrieval などが参照できる section budget accessor。

    Args:
        config: Runtime prompt budget config。
        profile: 参照対象の profile 名。
        section: 参照対象の section kind。

    Returns:
        指定 profile / section の runtime prompt section budget。
    """
    return config.profile_budget(profile).section_budget(section)


def memory_top_k_for_profile(config: RuntimePromptBudgetConfig, profile: PromptProfileName) -> int:
    """User memory retrieval が prompt budget から参照する item 上限。

    Args:
        config: Runtime prompt budget config。
        profile: 参照対象の profile 名。

    Returns:
        user memory section の max_items。
    """
    return section_budget_for_profile(config, profile, PromptSectionKind.USER_MEMORY).max_items


def project_context_top_k_for_profile(
    config: RuntimePromptBudgetConfig,
    profile: PromptProfileName,
) -> int:
    """Project context retrieval が prompt budget から参照する item 上限。

    Args:
        config: Runtime prompt budget config。
        profile: 参照対象の profile 名。

    Returns:
        project memory section の max_items。
    """
    return section_budget_for_profile(config, profile, PromptSectionKind.PROJECT_MEMORY).max_items


def apply_prompt_budget_toml(
    config: RuntimePromptBudgetConfig,
    table: TomlTable,
) -> RuntimePromptBudgetConfig:
    """TOML ``[prompt_budget]`` セクションを適用する。

    Args:
        config: 適用前の runtime prompt budget config。
        table: TOML の ``[prompt_budget]`` テーブル。

    Returns:
        TOML 値を反映した runtime prompt budget config。

    """
    value = config
    if "enabled" in table:
        value = replace(value, enabled=_parse_bool(table["enabled"], "prompt_budget.enabled"))
    if "chat_profile" in table:
        value = replace(
            value,
            chat_profile=_parse_profile_name(table["chat_profile"], "prompt_budget.chat_profile"),
        )
    if "proactive_profile" in table:
        value = replace(
            value,
            proactive_profile=_parse_profile_name(
                table["proactive_profile"], "prompt_budget.proactive_profile"
            ),
        )
    for profile_name in _PROMPT_PROFILE_NAMES:
        profile_table = _table_or_empty(
            table,
            profile_name.value,
            path=f"prompt_budget.{profile_name.value}",
        )
        value = _replace_profile_budget(
            value,
            profile_name,
            _apply_profile_toml(value.profile_budget(profile_name), profile_table, profile_name),
        )
    return validate_prompt_budget_config(value)


def validate_prompt_budget_config(config: RuntimePromptBudgetConfig) -> RuntimePromptBudgetConfig:
    """Prompt budget 設定の範囲と profile 不変条件を検証する。

    Args:
        config: 検証対象の runtime prompt budget config。

    Returns:
        section ごとに検証済みの runtime prompt budget config。

    Raises:
        ConfigError: budget 範囲または profile 不変条件が不正な場合。
    """
    value = replace(
        config,
        local_low=_validate_profile(config.local_low, PromptProfileName.LOCAL_LOW),
        local_balanced=_validate_profile(config.local_balanced, PromptProfileName.LOCAL_BALANCED),
        local_quality=_validate_profile(config.local_quality, PromptProfileName.LOCAL_QUALITY),
        proactive_short=_validate_profile(
            config.proactive_short, PromptProfileName.PROACTIVE_SHORT
        ),
    )
    if value.proactive_profile is not PromptProfileName.PROACTIVE_SHORT:
        profile = value.profile_budget(value.proactive_profile)
        chat_profile = value.profile_budget(value.chat_profile)
        if profile.total_max_chars > chat_profile.total_max_chars:
            message = "prompt_budget.proactive_profile must not exceed chat_profile total_max_chars"
            raise ConfigError(message)
    if value.proactive_short.total_max_chars >= value.local_balanced.total_max_chars:
        message = (
            "prompt_budget.proactive_short.total_max_chars must be shorter than local_balanced"
        )
        raise ConfigError(message)
    return value


def prompt_profile_names() -> tuple[PromptProfileName, ...]:
    """ConfigSpec 生成用の profile 名一覧。

    Returns:
        サポートする prompt profile 名の安定順 tuple。
    """
    return _PROMPT_PROFILE_NAMES


def prompt_section_kinds() -> tuple[PromptSectionKind, ...]:
    """ConfigSpec 生成用の section 名一覧。

    Returns:
        サポートする prompt section kind の安定順 tuple。
    """
    return _PROMPT_SECTION_KINDS


def prompt_overflow_behavior_values() -> tuple[str, ...]:
    """ConfigSpec 生成用の overflow behavior 値一覧。

    Returns:
        TOML schema に公開する overflow behavior 値の tuple。
    """
    return tuple(behavior.value for behavior in _PROMPT_OVERFLOW_BEHAVIORS)


def iter_profile_sections(
    profile: RuntimePromptProfileBudget,
) -> Iterable[tuple[PromptSectionKind, RuntimePromptSectionBudget]]:
    """Profile の section budget を安定順で列挙する。

    Args:
        profile: 列挙対象の runtime prompt profile budget。

    Yields:
        section kind と対応する runtime prompt section budget。
    """
    for section in _PROMPT_SECTION_KINDS:
        yield section, profile.section_budget(section)


def _replace_profile_budget(
    config: RuntimePromptBudgetConfig,
    profile_name: PromptProfileName,
    budget: RuntimePromptProfileBudget,
) -> RuntimePromptBudgetConfig:
    match profile_name:
        case PromptProfileName.LOCAL_LOW:
            return replace(config, local_low=budget)
        case PromptProfileName.LOCAL_BALANCED:
            return replace(config, local_balanced=budget)
        case PromptProfileName.LOCAL_QUALITY:
            return replace(config, local_quality=budget)
        case PromptProfileName.PROACTIVE_SHORT:
            return replace(config, proactive_short=budget)


def _replace_section_budget(
    profile: RuntimePromptProfileBudget,
    section: PromptSectionKind,
    budget: RuntimePromptSectionBudget,
) -> RuntimePromptProfileBudget:
    return RuntimePromptProfileBudget(
        total_max_chars=profile.total_max_chars,
        system=_section_value(profile.system, section, PromptSectionKind.SYSTEM, budget),
        persona=_section_value(profile.persona, section, PromptSectionKind.PERSONA, budget),
        safety_constraints=_section_value(
            profile.safety_constraints,
            section,
            PromptSectionKind.SAFETY_CONSTRAINTS,
            budget,
        ),
        recent_conversation=_section_value(
            profile.recent_conversation,
            section,
            PromptSectionKind.RECENT_CONVERSATION,
            budget,
        ),
        user_memory=_section_value(
            profile.user_memory, section, PromptSectionKind.USER_MEMORY, budget
        ),
        project_memory=_section_value(
            profile.project_memory, section, PromptSectionKind.PROJECT_MEMORY, budget
        ),
        relationship_signal=_section_value(
            profile.relationship_signal,
            section,
            PromptSectionKind.RELATIONSHIP_SIGNAL,
            budget,
        ),
        internal_state=_section_value(
            profile.internal_state, section, PromptSectionKind.INTERNAL_STATE, budget
        ),
        interaction_policy=_section_value(
            profile.interaction_policy,
            section,
            PromptSectionKind.INTERACTION_POLICY,
            budget,
        ),
        task_context=_section_value(
            profile.task_context, section, PromptSectionKind.TASK_CONTEXT, budget
        ),
        user_input=_section_value(
            profile.user_input, section, PromptSectionKind.USER_INPUT, budget
        ),
    )


def _section_value(
    current: RuntimePromptSectionBudget,
    section: PromptSectionKind,
    target: PromptSectionKind,
    replacement: RuntimePromptSectionBudget,
) -> RuntimePromptSectionBudget:
    if section is target:
        return replacement
    return current


def _apply_profile_toml(
    profile: RuntimePromptProfileBudget,
    table: TomlTable,
    profile_name: PromptProfileName,
) -> RuntimePromptProfileBudget:
    path = f"prompt_budget.{profile_name.value}"
    value = profile
    if "total_max_chars" in table:
        value = replace(
            value,
            total_max_chars=_parse_int(table["total_max_chars"], f"{path}.total_max_chars"),
        )
    for section in _PROMPT_SECTION_KINDS:
        section_table = _table_or_empty(table, section.value, path=f"{path}.{section.value}")
        value = _replace_section_budget(
            value,
            section,
            _apply_section_toml(
                value.section_budget(section), section_table, profile_name, section
            ),
        )
    return value


def _apply_section_toml(
    section_budget: RuntimePromptSectionBudget,
    table: TomlTable,
    profile_name: PromptProfileName,
    section: PromptSectionKind,
) -> RuntimePromptSectionBudget:
    path = f"prompt_budget.{profile_name.value}.{section.value}"
    return replace(
        section_budget,
        max_chars=_optional_int(table, "max_chars", path, section_budget.max_chars),
        max_items=_optional_int(table, "max_items", path, section_budget.max_items),
        priority=_optional_int(table, "priority", path, section_budget.priority),
        overflow_behavior=_optional_overflow_behavior(
            table,
            "overflow_behavior",
            path,
            section_budget.overflow_behavior,
        ),
    )


def _validate_profile(
    profile: RuntimePromptProfileBudget,
    name: PromptProfileName,
) -> RuntimePromptProfileBudget:
    if profile.total_max_chars <= 0:
        message = f"prompt_budget.{name.value}.total_max_chars must be greater than 0"
        raise ConfigError(message)
    required_max_chars = 0
    required_trusted_sections = 0
    for section in _PROMPT_SECTION_KINDS:
        budget = profile.section_budget(section)
        _validate_section(budget, name, section)
        if budget.overflow_behavior is PromptOverflowBehavior.REQUIRED:
            required_max_chars += budget.max_chars
            if section in {
                PromptSectionKind.SYSTEM,
                PromptSectionKind.SAFETY_CONSTRAINTS,
            }:
                required_trusted_sections += 1
    required_prompt_chars = required_max_chars + _trusted_required_separator_chars(
        required_trusted_sections
    )
    if required_prompt_chars > profile.total_max_chars:
        message = (
            f"prompt_budget.{name.value}.required section max_chars total "
            "including trusted separators must not exceed total_max_chars"
        )
        raise ConfigError(message)
    return profile


def _trusted_required_separator_chars(required_trusted_sections: int) -> int:
    if required_trusted_sections <= 1:
        return 0
    return (required_trusted_sections - 1) * len("\n\n")


def _validate_section(
    budget: RuntimePromptSectionBudget,
    profile: PromptProfileName,
    section: PromptSectionKind,
) -> None:
    path = f"prompt_budget.{profile.value}.{section.value}"
    if budget.max_chars < 0:
        message = f"{path}.max_chars must be greater than or equal to 0"
        raise ConfigError(message)
    if budget.max_items < 0:
        message = f"{path}.max_items must be greater than or equal to 0"
        raise ConfigError(message)
    if budget.priority < 0:
        message = f"{path}.priority must be greater than or equal to 0"
        raise ConfigError(message)
    if budget.overflow_behavior is PromptOverflowBehavior.REQUIRED:
        _validate_required_section_budget(budget, path, section)


def _validate_required_section_budget(
    budget: RuntimePromptSectionBudget,
    path: str,
    section: PromptSectionKind,
) -> None:
    if section not in _REQUIRED_PROMPT_SECTION_KINDS:
        allowed = ", ".join(kind.value for kind in _REQUIRED_PROMPT_SECTION_KINDS)
        message = f"{path}.required section must be one of: {allowed}"
        raise ConfigError(message)
    if budget.max_chars == 0:
        message = f"{path}.required section must have max_chars greater than 0"
        raise ConfigError(message)
    if budget.max_items == 0:
        message = f"{path}.required section must have max_items greater than 0"
        raise ConfigError(message)


def _optional_int(table: TomlTable, key: str, path: str, default: int) -> int:
    if key not in table:
        return default
    return _parse_int(table[key], f"{path}.{key}")


def _optional_overflow_behavior(
    table: TomlTable,
    key: str,
    path: str,
    default: PromptOverflowBehavior,
) -> PromptOverflowBehavior:
    if key not in table:
        return default
    return _parse_overflow_behavior(table[key], f"{path}.{key}")


def _parse_profile_name(value: TomlValue, path: str) -> PromptProfileName:
    raw = _parse_string(value, path)
    for profile in _PROMPT_PROFILE_NAMES:
        if raw == profile.value:
            return profile
    allowed = ", ".join(profile.value for profile in _PROMPT_PROFILE_NAMES)
    message = f"Invalid {path}: {raw}. Allowed values: {allowed}"
    raise ConfigError(message)


def _parse_overflow_behavior(value: TomlValue, path: str) -> PromptOverflowBehavior:
    raw = _parse_string(value, path)
    for behavior in _PROMPT_OVERFLOW_BEHAVIORS:
        if raw == behavior.value:
            return behavior
    allowed = ", ".join(behavior.value for behavior in _PROMPT_OVERFLOW_BEHAVIORS)
    message = f"Invalid {path}: {raw}. Allowed values: {allowed}"
    raise ConfigError(message)


def _table_or_empty(table: TomlTable, key: str, *, path: str) -> TomlTable:
    if key not in table:
        return {}
    value = table[key]
    if isinstance(value, dict):
        return value
    message = f"Runtime config value '{path}' must be a table"
    raise ConfigError(message)


def _parse_bool(value: TomlValue, path: str) -> bool:
    if isinstance(value, bool):
        return value
    message = f"Runtime config value '{path}' must be a boolean"
    raise ConfigError(message)


def _parse_int(value: TomlValue, path: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    message = f"Runtime config value '{path}' must be an integer"
    raise ConfigError(message)


def _parse_string(value: TomlValue, path: str) -> str:
    if isinstance(value, str):
        return value
    message = f"Runtime config value '{path}' must be a string"
    raise ConfigError(message)


def _section(
    max_chars: int,
    max_items: int,
    priority: int,
    overflow_behavior: PromptOverflowBehavior,
) -> RuntimePromptSectionBudget:
    return RuntimePromptSectionBudget(
        max_chars=max_chars,
        max_items=max_items,
        priority=priority,
        overflow_behavior=overflow_behavior,
    )


def _summary_truncate() -> PromptOverflowBehavior:
    return PromptOverflowBehavior.USE_EXISTING_SUMMARY_THEN_TRUNCATE


def _local_low_profile() -> RuntimePromptProfileBudget:
    return RuntimePromptProfileBudget(
        total_max_chars=6000,
        system=_section(1100, 1, 100, PromptOverflowBehavior.REQUIRED),
        persona=_section(500, 1, 95, PromptOverflowBehavior.TRUNCATE),
        safety_constraints=_section(900, 8, 98, PromptOverflowBehavior.TRUNCATE_ITEMS),
        recent_conversation=_section(1800, 6, 70, _summary_truncate()),
        user_memory=_section(800, 3, 55, PromptOverflowBehavior.TRUNCATE_ITEMS),
        project_memory=_section(500, 2, 45, PromptOverflowBehavior.TRUNCATE_ITEMS),
        relationship_signal=_section(450, 2, 65, PromptOverflowBehavior.TRUNCATE_ITEMS),
        internal_state=_section(550, 4, 60, PromptOverflowBehavior.TRUNCATE_ITEMS),
        interaction_policy=_section(500, 4, 75, PromptOverflowBehavior.TRUNCATE_ITEMS),
        task_context=_section(800, 4, 50, PromptOverflowBehavior.TRUNCATE_ITEMS),
        user_input=_section(1600, 1, 100, PromptOverflowBehavior.REQUIRED),
    )


def _local_balanced_profile() -> RuntimePromptProfileBudget:
    return RuntimePromptProfileBudget(
        total_max_chars=10000,
        system=_section(1400, 1, 100, PromptOverflowBehavior.REQUIRED),
        persona=_section(900, 1, 95, PromptOverflowBehavior.TRUNCATE),
        safety_constraints=_section(1200, 10, 98, PromptOverflowBehavior.TRUNCATE_ITEMS),
        recent_conversation=_section(3600, 12, 70, _summary_truncate()),
        user_memory=_section(1400, 5, 55, PromptOverflowBehavior.TRUNCATE_ITEMS),
        project_memory=_section(1000, 4, 45, PromptOverflowBehavior.TRUNCATE_ITEMS),
        relationship_signal=_section(700, 3, 65, PromptOverflowBehavior.TRUNCATE_ITEMS),
        internal_state=_section(800, 5, 60, PromptOverflowBehavior.TRUNCATE_ITEMS),
        interaction_policy=_section(700, 5, 75, PromptOverflowBehavior.TRUNCATE_ITEMS),
        task_context=_section(1200, 6, 50, PromptOverflowBehavior.TRUNCATE_ITEMS),
        user_input=_section(2400, 1, 100, PromptOverflowBehavior.REQUIRED),
    )


def _local_quality_profile() -> RuntimePromptProfileBudget:
    return RuntimePromptProfileBudget(
        total_max_chars=16000,
        system=_section(1800, 1, 100, PromptOverflowBehavior.REQUIRED),
        persona=_section(1400, 1, 95, PromptOverflowBehavior.TRUNCATE),
        safety_constraints=_section(1600, 12, 98, PromptOverflowBehavior.TRUNCATE_ITEMS),
        recent_conversation=_section(6400, 20, 70, _summary_truncate()),
        user_memory=_section(2400, 8, 55, PromptOverflowBehavior.TRUNCATE_ITEMS),
        project_memory=_section(1800, 6, 45, PromptOverflowBehavior.TRUNCATE_ITEMS),
        relationship_signal=_section(1000, 4, 65, PromptOverflowBehavior.TRUNCATE_ITEMS),
        internal_state=_section(1200, 6, 60, PromptOverflowBehavior.TRUNCATE_ITEMS),
        interaction_policy=_section(1000, 6, 75, PromptOverflowBehavior.TRUNCATE_ITEMS),
        task_context=_section(2000, 8, 50, PromptOverflowBehavior.TRUNCATE_ITEMS),
        user_input=_section(3200, 1, 100, PromptOverflowBehavior.REQUIRED),
    )


def _proactive_short_profile() -> RuntimePromptProfileBudget:
    return RuntimePromptProfileBudget(
        total_max_chars=3000,
        system=_section(900, 1, 100, PromptOverflowBehavior.REQUIRED),
        persona=_section(350, 1, 95, PromptOverflowBehavior.TRUNCATE),
        safety_constraints=_section(700, 6, 98, PromptOverflowBehavior.TRUNCATE_ITEMS),
        recent_conversation=_section(500, 3, 45, PromptOverflowBehavior.TRUNCATE_ITEMS),
        user_memory=_section(300, 1, 35, PromptOverflowBehavior.OMIT),
        project_memory=_section(0, 0, 20, PromptOverflowBehavior.OMIT),
        relationship_signal=_section(450, 2, 70, PromptOverflowBehavior.TRUNCATE_ITEMS),
        internal_state=_section(350, 3, 55, PromptOverflowBehavior.TRUNCATE_ITEMS),
        interaction_policy=_section(400, 3, 80, PromptOverflowBehavior.TRUNCATE_ITEMS),
        task_context=_section(450, 3, 50, PromptOverflowBehavior.TRUNCATE_ITEMS),
        user_input=_section(700, 1, 100, PromptOverflowBehavior.REQUIRED),
    )
