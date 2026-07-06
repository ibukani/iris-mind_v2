"""Iris global persona の共有契約。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PersonaProfile(BaseModel):
    """Runtime が prompt 構築に使う安定した global persona。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    version: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=1, max_length=160)
    identity: tuple[str, ...] = Field(min_length=1, max_length=12)
    values: tuple[str, ...] = Field(min_length=1, max_length=12)
    traits: tuple[str, ...] = Field(min_length=1, max_length=12)
    speech_style: tuple[str, ...] = Field(min_length=1, max_length=12)
    behavioral_tendencies: tuple[str, ...] = Field(min_length=1, max_length=12)
