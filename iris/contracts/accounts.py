"""Account identity context contracts."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.core.ids import AccountId, ActorId, ExternalRef


@dataclass(frozen=True)
class AccountProfile:
    """External account profile linked to an Iris actor."""

    account_id: AccountId
    provider: str
    provider_subject: ExternalRef
    display_name: str
    linked_actor_id: ActorId | None = None
    metadata: Mapping[str, str] = MappingProxyType({})
