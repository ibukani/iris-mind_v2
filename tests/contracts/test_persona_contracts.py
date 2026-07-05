"""PersonaProfile contract tests."""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from iris.contracts.persona import PersonaProfile


def test_persona_profile_validates_runtime_toml_shape() -> None:
    """persona.toml の machine-readable shape を typed contract に変換できる。"""
    profile = PersonaProfile.model_validate(
        {
            "schema_version": 1,
            "profile_version": "test-v1",
            "name": "Iris",
            "role": "AI companion",
            "core_values": ["support user agency"],
            "stable_traits": ["calm"],
            "speech_style": ["same language as latest user message"],
            "behavioral_guidelines": ["do not mutate global persona from memory"],
            "boundaries": ["safety constraints override persona"],
        }
    )

    assert profile.profile_version == "test-v1"
    assert profile.name == "Iris"


def test_persona_profile_rejects_unknown_account_or_space_policy_fields() -> None:
    """Account / space specific policy を global persona contract に混ぜない。"""
    with pytest.raises(ValidationError):
        PersonaProfile.model_validate(
            {
                "schema_version": 1,
                "profile_version": "test-v1",
                "name": "Iris",
                "role": "AI companion",
                "core_values": ["support user agency"],
                "stable_traits": ["calm"],
                "speech_style": ["same language as latest user message"],
                "behavioral_guidelines": ["do not mutate global persona from memory"],
                "boundaries": ["safety constraints override persona"],
                "account_specific_interaction_policy": ["always be casual with one user"],
            }
        )


def test_persona_profile_rejects_empty_sections() -> None:
    """安定personaに必要な主要sectionは空にしない。"""
    with pytest.raises(ValidationError):
        PersonaProfile(
            schema_version=1,
            profile_version="test-v1",
            name="Iris",
            role="AI companion",
            core_values=(),
            stable_traits=("calm",),
            speech_style=("same language as latest user message",),
            behavioral_guidelines=("do not mutate global persona from memory",),
            boundaries=("safety constraints override persona",),
        )
