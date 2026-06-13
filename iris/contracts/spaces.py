"""相互作用スペースの型付き契約。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from iris.core.metadata import EMPTY_METADATA, immutable_metadata

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.core.ids import ExternalRef, SpaceId


class SpaceKind(StrEnum):
    """相互作用スペースの種類。"""

    DIRECT_MESSAGE = "direct_message"
    TEXT_CHANNEL = "text_channel"
    THREAD = "thread"
    VOICE_CHANNEL = "voice_channel"
    ROOM = "room"
    BROADCAST = "broadcast"


@dataclass(frozen=True)
class InteractionSpace:
    """観察された相互作用スペースの安定した識別情報とコンテキスト。

    現在の在室者は保持しない。将来の SpaceOccupancyStore が在室者情報の
    正本を担う。
    """

    space_id: SpaceId
    space_kind: SpaceKind
    display_name: str
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """メタデータが強固に不変であることを保証する。"""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))


class SpaceBindingStoreError(ValueError):
    """SpaceBindingStore の障害発生時に送出される。"""


@dataclass(frozen=True)
class SpaceBinding:
    """外部プロバイダのスペースを Iris 内部の space_id にバインドする予約契約。

    デフォルトの Iris-Mind runtime は SpaceBinding を永続化せず、配線もしない。
    既定のspace解決は provider + provider_space_ref から決定論的に行う。
    """

    provider: str
    provider_space_ref: ExternalRef
    space_id: SpaceId
    display_name: str
    space_kind: SpaceKind
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """メタデータが強固に不変であることを保証する。"""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))
