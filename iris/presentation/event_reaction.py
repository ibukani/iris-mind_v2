"""イベント反応候補をPresentedOutputに変換するpresenter。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.actions import PresentedOutput

if TYPE_CHECKING:
    from iris.contracts.event_reaction import ReactionCandidate


@dataclass(frozen=True)
class EventReactionPresenter:
    """ReactionCandidateをPresentedOutputに変換する。"""

    def present(self, candidate: ReactionCandidate) -> PresentedOutput:
        """候補からPresentedOutputを生成する。

        Returns:
            PresentedOutput: 変換された出力。
        """
        return PresentedOutput(
            text=candidate.text,
            priority=candidate.priority,
            interruptible=candidate.interruptible,
            style_hint="event_reaction",
        )
