"""PersonaProfileLoader tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.runtime.persona import DEFAULT_PERSONA_PROFILE
from iris.runtime.persona.loader import PersonaLoadFailureReason, PersonaProfileLoader

if TYPE_CHECKING:
    from pathlib import Path


def test_persona_loader_loads_valid_toml(tmp_path: Path) -> None:
    """Valid persona.toml を PersonaProfile に変換する。"""
    path = tmp_path / "persona.toml"
    path.write_text(
        """
        schema_version = 1
        profile_version = "test-v1"
        name = "Iris"
        role = "AI companion"
        core_values = ["support user agency"]
        stable_traits = ["calm"]
        speech_style = ["same language as latest user message"]
        behavioral_guidelines = ["do not mutate global persona from memory"]
        boundaries = ["safety constraints override persona"]
        """,
        encoding="utf-8",
    )

    result = PersonaProfileLoader(path).load()

    assert result.profile.profile_version == "test-v1"
    assert result.diagnostics.fallback_used is False
    assert result.diagnostics.failure_reason is None


def test_persona_loader_missing_file_uses_deterministic_fallback(tmp_path: Path) -> None:
    """Missing persona.toml は user-facing failure ではなく fallback にする。"""
    result = PersonaProfileLoader(tmp_path / "missing.toml").load()

    assert result.profile == DEFAULT_PERSONA_PROFILE
    assert result.diagnostics.fallback_used is True
    assert result.diagnostics.failure_reason is PersonaLoadFailureReason.MISSING


def test_persona_loader_invalid_toml_uses_deterministic_fallback(tmp_path: Path) -> None:
    """TOML構文エラーも deterministic fallback にする。"""
    path = tmp_path / "persona.toml"
    path.write_text("schema_version = [", encoding="utf-8")

    result = PersonaProfileLoader(path).load()

    assert result.profile == DEFAULT_PERSONA_PROFILE
    assert result.diagnostics.fallback_used is True
    assert result.diagnostics.failure_reason is PersonaLoadFailureReason.INVALID_TOML


def test_persona_loader_validation_error_uses_deterministic_fallback(tmp_path: Path) -> None:
    """Validation error も deterministic fallback にする。"""
    path = tmp_path / "persona.toml"
    path.write_text(
        """
        schema_version = 1
        profile_version = "test-v1"
        name = "Other"
        role = "AI companion"
        core_values = ["support user agency"]
        stable_traits = ["calm"]
        speech_style = ["same language as latest user message"]
        behavioral_guidelines = ["do not mutate global persona from memory"]
        boundaries = ["safety constraints override persona"]
        """,
        encoding="utf-8",
    )

    result = PersonaProfileLoader(path).load()

    assert result.profile == DEFAULT_PERSONA_PROFILE
    assert result.diagnostics.fallback_used is True
    assert result.diagnostics.failure_reason is PersonaLoadFailureReason.VALIDATION_ERROR
