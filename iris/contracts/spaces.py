"""相互作用スペースの型付き契約。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.contracts.identity import Identity
    from iris.core.ids import ActorId, SpaceId


class SpaceKind(StrEnum):
    """相互作用スペースの種類。"""

    DIRECT_MESSAGE = "direct_message"
    CHANNEL = "channel"
    THREAD = "thread"
    ROOM = "room"
    BROADCAST = "broadcast"


class SpaceParticipantKind(StrEnum):
    """スペース参加者の種類。"""

    HUMAN = "human"
    DEVICE = "device"
    SERVICE = "service"
    SYSTEM = "system"
    IRIS = "iris"


@dataclass(frozen=True)
class SpaceParticipant:
    """スペース内の参加者エントリ。"""

    actor_id: ActorId
    participant_kind: SpaceParticipantKind
    display_name: str
    identity: Identity | None = None
    metadata: Mapping[str, str] = MappingProxyType({})


@dataclass(frozen=True)
class InteractionSpace:
    """観察された相互作用のコンテキストとなるスペース。"""

    space_id: SpaceId
    space_kind: SpaceKind
    display_name: str
    participants: tuple[SpaceParticipant, ...] = ()
    metadata: Mapping[str, str] = MappingProxyType({})
