"""プロアクティブ発話機能：顕著性に基づきIrisが会話を開始する。"""

from __future__ import annotations

from iris.features.proactive_talk.definition import (
    ProactiveActionSelectionStep,
    ProactivePolicyStep,
    define_proactive_talk_feature,
)
from iris.features.proactive_talk.goals import GoalProposer
from iris.features.proactive_talk.models import ProactiveGoal, ProactiveSalience
from iris.features.proactive_talk.scoring import SalienceScorer

__all__ = [
    "GoalProposer",
    "ProactiveActionSelectionStep",
    "ProactiveGoal",
    "ProactivePolicyStep",
    "ProactiveSalience",
    "SalienceScorer",
    "define_proactive_talk_feature",
]
