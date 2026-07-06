"""Machine-readable global persona profile を起動時に読み込む。"""

from __future__ import annotations

from importlib.resources import files
from io import BytesIO
import tomllib
from typing import TYPE_CHECKING

from pydantic import ValidationError

from iris.contracts.persona import PersonaProfile
from iris.runtime.config.parsing import load_toml

if TYPE_CHECKING:
    from pathlib import Path


FALLBACK_PERSONA_PROFILE = PersonaProfile(
    version="fallback-v1",
    name="Iris",
    role="安全で誠実な AI コンパニオン",
    identity=("Iris として直接応答する",),
    values=("安全性と誠実さを優先する", "不確かなことを断定しない"),
    traits=("落ち着いている", "実用的である"),
    speech_style=("相手の言語に合わせる", "簡潔で自然に話す"),
    behavioral_tendencies=("必要な情報を明確に伝える",),
)


class PersonaLoadResult(PersonaProfile):
    """検証済み profile と fallback 観測情報。"""

    used_fallback: bool = False
    failure_reason: str | None = None

    @classmethod
    def from_profile(
        cls,
        profile: PersonaProfile,
        *,
        used_fallback: bool,
        failure_reason: str | None,
    ) -> PersonaLoadResult:
        """Profile を load metadata 付き結果へ変換する。

        Returns:
            Metadata を付加した読み込み結果。
        """
        return cls(
            version=profile.version,
            name=profile.name,
            role=profile.role,
            identity=profile.identity,
            values=profile.values,
            traits=profile.traits,
            speech_style=profile.speech_style,
            behavioral_tendencies=profile.behavioral_tendencies,
            used_fallback=used_fallback,
            failure_reason=failure_reason,
        )

    def profile(self) -> PersonaProfile:
        """Prompt boundary に渡す純粋な persona contract を返す。

        Returns:
            Loader metadata を含まない persona profile。
        """
        return PersonaProfile(
            version=self.version,
            name=self.name,
            role=self.role,
            identity=self.identity,
            values=self.values,
            traits=self.traits,
            speech_style=self.speech_style,
            behavioral_tendencies=self.behavioral_tendencies,
        )


class PersonaProfileLoader:
    """TOML 全体を検証し、失敗時は完全な fallback へ切り替える。"""

    def load(self, path: Path) -> PersonaLoadResult:
        """Persona TOML を読み込む。部分的な値は一切採用しない。

        Returns:
            検証済み profile または完全な fallback。
        """
        try:
            with path.open("rb") as file:
                raw = load_toml(file)
            profile = PersonaProfile.model_validate(raw)
        except FileNotFoundError:
            return self._fallback("persona file not found")
        except tomllib.TOMLDecodeError as exc:
            return self._fallback(f"invalid TOML: {exc}")
        except ValidationError as exc:
            return self._fallback(f"profile validation failed: {exc}")
        return PersonaLoadResult.from_profile(
            profile,
            used_fallback=False,
            failure_reason=None,
        )

    def load_default(self) -> PersonaLoadResult:
        """Package に同梱した global persona 正本を読み込む。

        Returns:
            検証済み profile または完全な fallback。
        """
        resource = files("iris.runtime.persona").joinpath("persona.toml")
        try:
            raw = load_toml(BytesIO(resource.read_bytes()))
            profile = PersonaProfile.model_validate(raw)
        except (FileNotFoundError, tomllib.TOMLDecodeError, ValidationError) as exc:
            return self._fallback(f"packaged persona load failed: {exc}")
        return PersonaLoadResult.from_profile(
            profile,
            used_fallback=False,
            failure_reason=None,
        )

    @staticmethod
    def _fallback(reason: str) -> PersonaLoadResult:
        return PersonaLoadResult.from_profile(
            FALLBACK_PERSONA_PROFILE,
            used_fallback=True,
            failure_reason=reason,
        )
