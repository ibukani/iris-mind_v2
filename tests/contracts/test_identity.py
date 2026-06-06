"""Tests for Identity contracts."""
from __future__ import annotations

import pytest

from iris.contracts.identity import ActorKind, Identity
from iris.core.ids import ActorId


def test_identity_metadata_is_defensively_copied() -> None:
    """Identity defensively copies metadata."""
    metadata = {"source": "discord"}
    identity = Identity(
        actor_id=ActorId("actor-1"),
        actor_kind=ActorKind.HUMAN,
        display_name="Mina",
        metadata=metadata,
    )

    metadata["source"] = "changed"

    assert identity.metadata["source"] == "discord"
    with pytest.raises(TypeError):
        identity.metadata["new"] = "value"  # type: ignore[index]  # testing immutability
