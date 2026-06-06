"""Shared external reference DTOs."""

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
    """Represents an external provider account/user reference."""

    provider: str
    provider_subject: ExternalRef
    display_name: str
    actor_kind: ActorKind = ActorKind.HUMAN
    account_id: AccountId | None = None
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """Defensively copy metadata as an immutable mapping proxy."""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))


@dataclass(frozen=True)
class ExternalSpaceRef:
    """Represents an external provider interaction space."""

    provider: str
    provider_space_ref: ExternalRef
    display_name: str
    space_kind: SpaceKind
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """Defensively copy metadata as an immutable mapping proxy."""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))
