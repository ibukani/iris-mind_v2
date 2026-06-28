"""外部参照の共有 DTO。"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.identity import ActorKind
from iris.contracts.spaces import SpaceKind
from iris.core.ids import AccountId, ExternalRef
from iris.core.metadata import EMPTY_METADATA, immutable_metadata


class ExternalAccountRef(BaseModel):
    """外部プロバイダのアカウント/ユーザー参照を表す。"""

    model_config = ConfigDict(frozen=True)

    provider: str
    provider_subject: ExternalRef
    display_name: str
    actor_kind: ActorKind = ActorKind.HUMAN
    account_id: AccountId | None = None
    metadata: Mapping[str, str] = Field(default_factory=dict)

    def model_post_init(self, __context: object) -> None:
        """メタデータを不変な mapping proxy として防御的にコピーする。"""
        if self.metadata is not EMPTY_METADATA:
            object.__setattr__(self, "metadata", immutable_metadata(self.metadata))


class ExternalSpaceRef(BaseModel):
    """外部プロバイダの相互作用スペースを表す。"""

    model_config = ConfigDict(frozen=True)

    provider: str
    provider_space_ref: ExternalRef
    display_name: str
    space_kind: SpaceKind
    metadata: Mapping[str, str] = Field(default_factory=dict)

    def model_post_init(self, __context: object) -> None:
        """メタデータを不変な mapping proxy として防御的にコピーする。"""
        if self.metadata is not EMPTY_METADATA:
            object.__setattr__(self, "metadata", immutable_metadata(self.metadata))
