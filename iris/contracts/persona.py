"""Iris global persona の runtime-readable 契約。"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

PersonaText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PersonaItemList = Annotated[tuple[PersonaText, ...], Field(min_length=1, max_length=20)]


class PersonaProfile(BaseModel):
    """`persona.toml` から読み込む global persona profile。

    account / space specific interaction policy は別境界で扱う。ここでは Iris 全体で
    安定して共有する人格情報だけを保持する。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    profile_version: PersonaText
    name: PersonaText
    role: PersonaText
    core_values: PersonaItemList
    stable_traits: PersonaItemList
    speech_style: PersonaItemList
    behavioral_guidelines: PersonaItemList
    boundaries: PersonaItemList

    @model_validator(mode="after")
    def _validate_global_profile(self) -> PersonaProfile:
        """Global persona として空洞化した profile を拒否する。

        Returns:
            PersonaProfile: 検証済みの profile。

        Raises:
            ValueError: Iris 以外の global persona 名が指定された場合。
        """
        if self.name.lower() != "iris":
            message = "global persona name must be Iris"
            raise ValueError(message)
        return self
