"""感情ベースライン状態の永続化契約。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

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


class AffectBaselineRecord(BaseModel):
    """Iris の感情ベースラインまたは actor 別 affect state。"""

    model_config = ConfigDict(frozen=True)

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

    @field_validator("scope", mode="before")
    @classmethod
    def _validate_scope(cls, scope: object) -> object:
        """未知のscopeへ安定したdomain errorを返す。

        Returns:
            Pydanticのenum変換へ渡すscope。

        Raises:
            ValueError: scopeが既知値でない場合。
        """
        if scope not in {AffectScope.GLOBAL, AffectScope.ACTOR}:
            msg = f"unknown affect scope: {scope}"
            raise ValueError(msg)
        return scope

    @model_validator(mode="after")
    def _validate_record(self) -> AffectBaselineRecord:
        """Scope と actor_id の整合性、および VAD 値を検証する。

        Returns:
            検証済みrecord。

        Raises:
            ValueError: scope、VAD、versionの不変条件に違反した場合。
        """
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
        return self


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
