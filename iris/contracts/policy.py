"""制約とアクション優先度のポリシー契約。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyConstraint:
    """応答動作をブロックまたは変更するポリシー制約。"""

    name: str
    reason: str
    prompt_instruction: str | None = None
    blocks_response: bool = False


@dataclass(frozen=True)
class ActionPreference:
    """アクション優先度に影響するプリファレンス。"""

    name: str
    reason: str
    priority_delta: int = 0
