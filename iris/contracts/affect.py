"""感情ベースライン状態の永続化契約。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime

    from iris.core.ids import ActorId, ObservationId


class AffectScope(StrEnum):
    """感情ベースラインのスコープ。"""

    GLOBAL = "global"
    ACTOR = "actor"


def _validate_vad(value: float, *, field_name: str) -> None:
    """VAD 値が [-1.0, 1.0] に収まることを検証する。

    Raises:
        ValueError: 値が指定範囲外の場合。
    """
    if not -1.0 <= value <= 1.0:
        msg = f"{field_name} must be between -1.0 and 1.0: {value}"
        raise ValueError(msg)


@dataclass(frozen=True)
class AffectBaselineRecord:
    """Iris の感情ベースラインまたは actor 別 affect state。"""

    scope: AffectScope
    actor_id: ActorId | None = None
    mood_label: str | None = None
    valence: float = 0.0
    arousal: float = 0.0
    dominance: float = 0.0
    affect_summary: str | None = None
    source_observation_id: ObservationId | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    version: int = 1

    def __post_init__(self) -> None:
        """Scope と actor_id の整合性、および VAD 値を検証する。

        Raises:
            ValueError: scope と actor_id の組み合わせまたは VAD 値が不正な場合。
        """
        if self.scope not in AffectScope:
            msg = f"unknown affect scope: {self.scope}"
            raise ValueError(msg)
        if self.scope == AffectScope.GLOBAL and self.actor_id is not None:
            msg = "global affect baseline must not have actor_id"
            raise ValueError(msg)
        if self.scope == AffectScope.ACTOR and self.actor_id is None:
            msg = "actor-scoped affect baseline requires actor_id"
            raise ValueError(msg)
        _validate_vad(self.valence, field_name="valence")
        _validate_vad(self.arousal, field_name="arousal")
        _validate_vad(self.dominance, field_name="dominance")
        if self.version < 1:
            msg = "version must be greater than or equal to 1"
            raise ValueError(msg)


class AffectStore(Protocol):
    """Iris affect baseline を保存するストア。"""

    async def get_global(self) -> AffectBaselineRecord | None:
        """Global affect baseline を取得する。"""
        ...

    async def upsert_global(self, record: AffectBaselineRecord) -> AffectBaselineRecord:
        """Global affect baseline を保存し、保存後の値を返す。"""
        ...

    async def get_for_actor(self, actor_id: ActorId) -> AffectBaselineRecord | None:
        """actor-scoped affect baseline を取得する。"""
        ...

    async def upsert_for_actor(self, record: AffectBaselineRecord) -> AffectBaselineRecord:
        """actor-scoped affect baseline を保存し、保存後の値を返す。"""
        ...
