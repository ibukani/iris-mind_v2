"""Account アイデンティティコンテキストの契約。"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.metadata import ImmutableMetadata
from iris.core.ids import AccountId, ActorId, ExternalRef
from iris.core.metadata import immutable_metadata


class AccountStoreError(ValueError):
    """Account ストレージまたはリンクのエラー。"""


class AccountProfile(BaseModel):
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

    model_config = ConfigDict(frozen=True)

    account_id: AccountId
    provider: str
    provider_subject: ExternalRef
    display_name: str
    linked_actor_id: ActorId | None = None
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


class AccountStore(Protocol):
    """External account profile storage and linking protocol.

    This is a pure data access interface. Domain logic such as validating
    account links or resolving identities should be performed by the caller.
    """

    async def get_by_external_ref(
        self,
        *,
        provider: str,
        provider_subject: ExternalRef,
    ) -> AccountProfile | None:
        """Get an account profile by provider and subject."""
        ...

    async def get_by_account_id(
        self,
        account_id: AccountId,
    ) -> AccountProfile | None:
        """Get an account profile by its internal AccountId."""
        ...

    async def put(
        self,
        account: AccountProfile,
    ) -> AccountProfile:
        """Create or update an account profile."""
        ...
