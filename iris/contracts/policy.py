"""制約とアクション優先度のポリシー契約。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PolicyConstraint(BaseModel):
    """応答動作をブロックまたは変更するポリシー制約。"""

    model_config = ConfigDict(frozen=True)

    name: str
    reason: str
    prompt_instruction: str | None = None
    blocks_response: bool = False


class ActionPreference(BaseModel):
    """アクション優先度に影響するプリファレンス。"""

    model_config = ConfigDict(frozen=True)

    name: str
    reason: str
    priority_delta: int = 0
