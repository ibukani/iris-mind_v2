"""外部参照の共有 DTO。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.identity import ActorKind
from iris.core.metadata import EMPTY_METADATA, immutable_metadata

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.contracts.spaces import SpaceKind
    from iris.core.ids import AccountId, ExternalRef


@dataclass(frozen=True)
class ExternalAccountRef:
    """外部プロバイダのアカウント/ユーザー参照を表す。"""

    provider: str
    provider_subject: ExternalRef
    display_name: str
    actor_kind: ActorKind = ActorKind.HUMAN
    account_id: AccountId | None = None
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """メタデータを不変な mapping proxy として防御的にコピーする。"""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))


@dataclass(frozen=True)
class ExternalSpaceRef:
    """外部プロバイダの相互作用スペースを表す。"""

    provider: str
    provider_space_ref: ExternalRef
    display_name: str
    space_kind: SpaceKind
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """メタデータを不変な mapping proxy として防御的にコピーする。"""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))
