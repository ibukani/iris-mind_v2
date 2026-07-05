"""SystemPromptBuilder tests."""

from __future__ import annotations

from iris.contracts.prompting import PromptSectionKind, PromptTrustBoundary
from iris.runtime.persona import DEFAULT_PERSONA_PROFILE
from iris.runtime.prompting.system_prompt import SystemPromptBuilder


def test_system_prompt_builder_generates_trusted_persona_section() -> None:
    """PersonaProfile から PromptSectionKind.PERSONA の trusted section を生成する。"""
    section = SystemPromptBuilder(DEFAULT_PERSONA_PROFILE).persona_section()

    assert section is not None
    assert section.kind is PromptSectionKind.PERSONA
    assert section.trust_boundary is PromptTrustBoundary.TRUSTED
    assert "Profile version: fallback-1" in section.content
    assert "safety" in section.content.lower()


def test_system_prompt_builder_without_persona_is_empty() -> None:
    """未設定時は既存 prompt assembly を変えない。"""
    builder = SystemPromptBuilder()

    assert builder.persona_section() is None
    assert builder.sections() == ()


def test_system_prompt_builder_sections_are_domain_neutral() -> None:
    """Chat / proactive / event reaction prompt が同じ persona section を再利用できる。"""
    builder = SystemPromptBuilder(DEFAULT_PERSONA_PROFILE)

    sections = builder.sections()

    assert len(sections) == 1
    assert sections[0] == builder.persona_section()
    assert sections[0].kind is PromptSectionKind.PERSONA
    assert sections[0].trust_boundary is PromptTrustBoundary.TRUSTED
