"""イベント反応の判定ポリシー。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.activity import ActivityKind
from iris.contracts.availability import AvailabilityStatus

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class EventReactionPolicy:
    """observation kindとavailabilityに応じて反応許可を決める。"""

    kind_availability: Mapping[ActivityKind, frozenset[AvailabilityStatus | None]]

    def allows(
        self,
        kind: ActivityKind,
        status: AvailabilityStatus | None,
    ) -> bool:
        """指定されたactivity kindとavailabilityで反応を許可するか返す。

        Args:
            kind: 判定対象のactivity kind。
            status: 判定対象のavailability status。

        Returns:
            bool: 許可される場合はTrue。
        """
        allowed = self.kind_availability.get(kind)
        if allowed is None:
            return False
        return status in allowed


def default_event_reaction_policy() -> EventReactionPolicy:
    """デフォルトの反応ポリシーを返す。

    - VOICE_JOINED: AVAILABLE / INTERRUPTIBLE / PASSIVE で反応。
    - APP_OPENED: AVAILABLE / INTERRUPTIBLE で反応。
    - それ以外の activity kind は反応しない。

    Returns:
        EventReactionPolicy: デフォルトポリシー。
    """
    return EventReactionPolicy(
        kind_availability={
            ActivityKind.VOICE_JOINED: frozenset(
                {
                    AvailabilityStatus.AVAILABLE,
                    AvailabilityStatus.INTERRUPTIBLE,
                    AvailabilityStatus.PASSIVE,
                }
            ),
            ActivityKind.APP_OPENED: frozenset(
                {
                    AvailabilityStatus.AVAILABLE,
                    AvailabilityStatus.INTERRUPTIBLE,
                }
            ),
        },
    )
