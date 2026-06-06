"""Account アイデンティティコンテキストの契約。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.core.metadata import EMPTY_METADATA, immutable_metadata

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.core.ids import AccountId, ActorId, ExternalRef


class AccountStoreError(ValueError):
    """Account ストレージまたはリンクのエラー。"""


@dataclass(frozen=True)
class AccountProfile:
    """外部プロバイダのアカウントバインディング。

    AccountProfile は外部プロバイダのアカウントバインディングを表す。
    Actor そのものではない。
    linked_actor_id を介して Iris Actor へリンクされることがある。

    account_id: この外部アカウントバインディングに対する Iris 内部 ID。
    provider: 外部プロバイダ名 (例: discord, github, cli, device)。
    provider_subject: プロバイダローカルで安定なアカウント ID。
    display_name: アカウントの表示名。
    linked_actor_id: このアカウントがリンクされている Iris 内部 ActorId。
    metadata: プロバイダから渡された追加コンテキスト。
    """

    account_id: AccountId
    provider: str
    provider_subject: ExternalRef
    display_name: str
    linked_actor_id: ActorId | None = None
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """メタデータを不変な mapping proxy として防御的にコピーする。"""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))
