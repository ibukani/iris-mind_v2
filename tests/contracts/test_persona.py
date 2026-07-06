"""PersonaProfile contract tests。"""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from iris.contracts.persona import PersonaProfile


def test_persona_profile_rejects_unknown_and_empty_fields() -> None:
    """不完全または未知 field を持つ profile は validation を通らない。"""
    with pytest.raises(ValidationError):
        PersonaProfile.model_validate(
            {
                "version": "1",
                "name": "Iris",
                "role": "companion",
                "identity": [],
                "values": ["honest"],
                "traits": ["calm"],
                "speech_style": ["concise"],
                "behavioral_tendencies": ["helpful"],
                "account_policy": "forbidden",
            }
        )
