"""PersonaProfile から trusted prompt section を決定論的に構築する。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.contracts.prompting import PromptSectionInput, PromptSectionKind, PromptTrustBoundary

if TYPE_CHECKING:
    from iris.contracts.persona import PersonaProfile


class SystemPromptBuilder:
    """Chat / proactive / event reaction で共有する persona section builder。"""

    def __init__(
        self,
        profile: PersonaProfile,
        *,
        used_fallback: bool = False,
        failure_reason: str | None = None,
    ) -> None:
        """起動時に検証済み profile を固定する。"""
        self._profile = profile
        self._used_fallback = used_fallback
        self._failure_reason = failure_reason

    @property
    def profile_version(self) -> str:
        """Observability に使う profile version。"""
        return self._profile.version

    @property
    def used_fallback(self) -> bool:
        """Loader fallback が使われたかを返す。"""
        return self._used_fallback

    @property
    def failure_reason(self) -> str | None:
        """Loader fallback の診断理由を返す。"""
        return self._failure_reason

    def build_persona_section(self) -> PromptSectionInput:
        """安定した項目順で trusted persona section を生成する。

        Returns:
            Prompt budget 適用前の PERSONA section。
        """
        profile = self._profile
        lines = (
            f"Name: {profile.name}",
            f"Role: {profile.role}",
            _render_items("Identity", profile.identity),
            _render_items("Core values", profile.values),
            _render_items("Personality traits", profile.traits),
            _render_items("Speech style", profile.speech_style),
            _render_items("Behavioral tendencies", profile.behavioral_tendencies),
        )
        return PromptSectionInput(
            kind=PromptSectionKind.PERSONA,
            title="Global Iris persona",
            trust_boundary=PromptTrustBoundary.TRUSTED,
            content="\n".join(lines),
        )


def _render_items(title: str, items: tuple[str, ...]) -> str:
    return f"{title}: " + "; ".join(items)
