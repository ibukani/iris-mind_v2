"""外部providerから見えるactor presence契約。"""

from __future__ import annotations

from enum import StrEnum


class PresenceStatus(StrEnum):
    """外部providerから見えるactorのpresence状態。"""

    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    AWAY = "away"
    IDLE = "idle"
    DO_NOT_DISTURB = "do_not_disturb"
    INVISIBLE = "invisible"
