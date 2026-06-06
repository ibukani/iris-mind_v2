"""Shared participant conversion helper for AppGateway."""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.contracts.spaces import SpaceParticipant, SpaceParticipantKind

if TYPE_CHECKING:
    from iris.contracts.identity import Identity


def space_participant_from_identity(identity: Identity) -> SpaceParticipant:
    """Create a SpaceParticipant snapshot from an Identity.

    Args:
        identity: The identity to snapshot.

    Returns:
        SpaceParticipant: A snapshot of the participant.
    """
    return SpaceParticipant(
        actor_id=identity.actor_id,
        participant_kind=SpaceParticipantKind(identity.actor_kind.value),
        display_name=identity.display_name,
        identity=identity,
        metadata=dict(identity.metadata),
    )
