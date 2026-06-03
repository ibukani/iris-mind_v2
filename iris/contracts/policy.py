from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyConstraint:
    name: str
    reason: str
    prompt_instruction: str | None = None
    blocks_response: bool = False


@dataclass(frozen=True)
class ActionPreference:
    name: str
    reason: str
    priority_delta: int = 0
