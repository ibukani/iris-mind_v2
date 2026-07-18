"""Provider-neutralな提示ヒント契約。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PresentationModality(StrEnum):
    """Producerが要求する汎用提示意図。"""

    TEXT = "text"
    VOICE = "voice"
    BOTH = "both"
    NOTIFICATION = "notification"
    UNKNOWN = "unknown"


class PresentationHints(BaseModel):
    """不変なprovider-neutral提示意図。

    adapterが内容をどう提示できるかを表す。配送許可、安全性policy、adapterのmodality対応を保証しない。
    """

    model_config = ConfigDict(frozen=True)

    style_hint: str | None = None
    emotion_hint: str | None = None
    expression_hint: str | None = None
    delay_ms: int = Field(default=0, ge=0)
    priority: int = 0
    interruptible: bool = True
    modality: PresentationModality = PresentationModality.UNKNOWN
