"""External AppGateway ingress models and DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.core.metadata import EMPTY_METADATA, immutable_metadata

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from iris.contracts.external_refs import ExternalAccountRef, ExternalSpaceRef
    from iris.core.ids import DeviceId, ExternalRef, SessionId


@dataclass(frozen=True)
class ActorMessagePayload:
    """Represents the actual actor message content and message-specific metadata."""

    text: str
    external_message_id: ExternalRef | None = None
    occurred_at: datetime | None = None


@dataclass(frozen=True)
class ActorMessageIngress:
    """Represents the full command/input for creating an ActorMessageObservation."""

    actor: ExternalAccountRef
    message: ActorMessagePayload
    session_id: SessionId
    space: ExternalSpaceRef | None = None
    device_id: DeviceId | None = None
    source: str | None = None
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """Defensively copy metadata as an immutable mapping proxy."""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))
