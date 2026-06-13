"""外部の非message activity event契約。"""

from __future__ import annotations

from enum import StrEnum


class ActivityKind(StrEnum):
    """外部providerから届く非message activity eventの種類。"""

    ACTOR_TYPING_STARTED = "actor_typing_started"
    ACTOR_TYPING_STOPPED = "actor_typing_stopped"
    APP_OPENED = "app_opened"
    APP_CLOSED = "app_closed"
    VOICE_JOINED = "voice_joined"
    VOICE_LEFT = "voice_left"
    SPACE_MESSAGE = "space_message"
    SYSTEM_INTERACTION = "system_interaction"
