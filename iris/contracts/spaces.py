"""相互作用スペースの型付き契約。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from iris.core.metadata import EMPTY_METADATA, immutable_metadata

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.contracts.identity import Identity
    from iris.core.ids import ActorId, ExternalRef, SpaceId


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
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """Ensure metadata is strongly immutable."""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))


@dataclass(frozen=True)
class InteractionSpace:
    """観察された相互作用のコンテキストとなるスペース。"""

    space_id: SpaceId
    space_kind: SpaceKind
    display_name: str
    participants: tuple[SpaceParticipant, ...] = ()
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """Ensure metadata is strongly immutable."""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))


class SpaceBindingStoreError(ValueError):
    """Raised on SpaceBindingStore failures."""


@dataclass(frozen=True)
class SpaceBinding:
    """External provider space binding to an Iris internal space_id."""

    provider: str
    provider_space_ref: ExternalRef
    space_id: SpaceId
    display_name: str
    space_kind: SpaceKind
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """Ensure metadata is strongly immutable."""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))
