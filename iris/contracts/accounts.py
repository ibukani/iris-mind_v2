"""Account identity context contracts."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.core.ids import AccountId, ActorId, ExternalRef


class AccountStoreError(ValueError):
    """Account storage or linking error."""


@dataclass(frozen=True)
class AccountProfile:
    """External provider account binding.

    AccountProfile represents an external provider account binding.
    It is not an Actor.
    It may be linked to an Iris Actor through linked_actor_id.

    account_id: Iris internal ID for this external account binding.
    provider: External provider name (e.g., discord, github, cli, device).
    provider_subject: Provider-local stable account ID.
    display_name: Display name for the account.
    linked_actor_id: Iris internal ActorId this account is linked to.
    metadata: Extra context from the provider.
    """

    account_id: AccountId
    provider: str
    provider_subject: ExternalRef
    display_name: str
    linked_actor_id: ActorId | None = None
    metadata: Mapping[str, str] = MappingProxyType({})
