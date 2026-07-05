"""`persona.toml` を typed persona profile に変換する loader。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import tomllib

from pydantic import ValidationError

from iris.contracts.persona import PersonaProfile
from iris.runtime.persona.defaults import DEFAULT_PERSONA_PROFILE


class PersonaLoadFailureReason(StrEnum):
    """User-facing failure に直結させない loader failure reason。"""

    MISSING = "missing"
    INVALID_TOML = "invalid_toml"
    VALIDATION_ERROR = "validation_error"


@dataclass(frozen=True)
class PersonaLoadDiagnostics:
    """Persona load の安全な observability metadata。"""

    fallback_used: bool
    failure_reason: PersonaLoadFailureReason | None
    profile_version: str


@dataclass(frozen=True)
class PersonaProfileLoadResult:
    """Persona profile と load 診断情報。"""

    profile: PersonaProfile
    diagnostics: PersonaLoadDiagnostics


class PersonaProfileLoader:
    """Machine-readable persona TOML を読み込み、失敗時は決定論的 fallback を返す。"""

    def __init__(
        self,
        path: str | Path = "persona.toml",
        *,
        fallback_profile: PersonaProfile = DEFAULT_PERSONA_PROFILE,
    ) -> None:
        """読み込み path と fallback profile を受け取る。"""
        self._path = Path(path)
        self._fallback_profile = fallback_profile

    @property
    def path(self) -> Path:
        """読み込み対象の path。"""
        return self._path

    def load(self) -> PersonaProfileLoadResult:
        """persona.toml を読み込む。失敗時は deterministic fallback を返す。

        Returns:
            PersonaProfileLoadResult: profile と安全な load diagnostics。
        """
        try:
            document: object = tomllib.loads(self._path.read_text(encoding="utf-8"))
            profile = PersonaProfile.model_validate(document)
        except FileNotFoundError:
            return self._fallback(PersonaLoadFailureReason.MISSING)
        except tomllib.TOMLDecodeError:
            return self._fallback(PersonaLoadFailureReason.INVALID_TOML)
        except ValidationError:
            return self._fallback(PersonaLoadFailureReason.VALIDATION_ERROR)
        return PersonaProfileLoadResult(
            profile=profile,
            diagnostics=PersonaLoadDiagnostics(
                fallback_used=False,
                failure_reason=None,
                profile_version=profile.profile_version,
            ),
        )

    def _fallback(self, reason: PersonaLoadFailureReason) -> PersonaProfileLoadResult:
        profile = self._fallback_profile
        return PersonaProfileLoadResult(
            profile=profile,
            diagnostics=PersonaLoadDiagnostics(
                fallback_used=True,
                failure_reason=reason,
                profile_version=profile.profile_version,
            ),
        )
