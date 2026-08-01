"""配送先ユーザーの opt-out / mute / block / interruption 制御の型付き契約。"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class UserControlState(BaseModel):
    """配送先 target_key ごとのユーザー制御状態。"""

    model_config = ConfigDict(frozen=True)

    opt_out: bool = False
    muted: bool = False
    blocked: bool = False
    interruptions_allowed: bool = True
    updated_at: datetime


class DeliveryUserControlStore(Protocol):
    """配送先ユーザーの制御状態を保持する port。"""

    async def get(self, target_key: str) -> UserControlState | None:
        """Target の制御状態を返す。

        Returns:
            保存済み状態。未保存なら None。
        """
        ...

    async def set(self, target_key: str, state: UserControlState) -> None:
        """Target の制御状態を保存する。"""
        ...
