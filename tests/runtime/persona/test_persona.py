"""Persona loader と prompt builder tests。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.contracts.prompting import PromptSectionKind, PromptTrustBoundary
from iris.runtime.persona import PersonaProfileLoader, SystemPromptBuilder

if TYPE_CHECKING:
    from pathlib import Path


def test_persona_loader_reads_repository_source_of_truth() -> None:
    """Repository の persona.toml は完全な typed profile として読める。"""
    result = PersonaProfileLoader().load_default()

    assert result.used_fallback is False
    assert result.failure_reason is None
    assert result.name == "Iris"
    assert result.version == "1"


def test_persona_loader_uses_complete_fallback_for_missing_file(tmp_path: Path) -> None:
    """Missing file は決定論的 fallback に切り替わる。"""
    result = PersonaProfileLoader().load(tmp_path / "missing.toml")

    assert result.used_fallback is True
    assert result.failure_reason == "persona file not found"
    assert result.version == "fallback-v1"
    assert result.values


def test_persona_loader_uses_complete_fallback_for_invalid_file(tmp_path: Path) -> None:
    """Malformed profile の部分値を採用せず、完全な fallback に切り替える。"""
    path = tmp_path / "persona.toml"
    path.write_text('version = "unsafe-partial"\nname = "Injected"\n', encoding="utf-8")

    result = PersonaProfileLoader().load(path)

    assert result.used_fallback is True
    assert result.failure_reason is not None
    assert result.version == "fallback-v1"
    assert result.name == "Iris"


def test_system_prompt_builder_is_deterministic_and_trusted() -> None:
    """同じ profile は同じ PERSONA trusted section を生成する。"""
    loaded = PersonaProfileLoader().load_default()
    builder = SystemPromptBuilder(loaded.profile())

    first = builder.build_persona_section()
    second = builder.build_persona_section()

    assert first == second
    assert first.kind is PromptSectionKind.PERSONA
    assert first.trust_boundary is PromptTrustBoundary.TRUSTED
    assert "Iris" in first.content
