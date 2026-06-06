"""External AppGateway ingress models and DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from iris.contracts.identity import ActorKind

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from iris.contracts.spaces import SpaceKind
    from iris.core.ids import AccountId, DeviceId, ExternalRef, SessionId


@dataclass(frozen=True)
class ExternalAccountRef:
    """Represents an external provider account/user reference."""

    provider: str
    provider_subject: ExternalRef
    display_name: str
    actor_kind: ActorKind = ActorKind.HUMAN
    account_id: AccountId | None = None
    metadata: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        """Defensively copy metadata as an immutable mapping proxy."""
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class ExternalSpaceRef:
    """Represents an external provider interaction space."""

    provider: str
    provider_space_ref: ExternalRef
    display_name: str
    space_kind: SpaceKind
    metadata: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        """Defensively copy metadata as an immutable mapping proxy."""
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class ActorMessagePayload:
    """Represents the actual actor message content and message-specific metadata."""

    text: str
    external_message_id: ExternalRef | None = None
    occurred_at: datetime | None = None
    metadata: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        """Defensively copy metadata as an immutable mapping proxy."""
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class ActorMessageIngress:
    """Represents the full command/input for creating an ActorMessageObservation."""

    actor: ExternalAccountRef
    message: ActorMessagePayload
    session_id: SessionId
    space: ExternalSpaceRef | None = None
    device_id: DeviceId | None = None
    source: str | None = None
    metadata: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        """Defensively copy metadata as an immutable mapping proxy."""
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
