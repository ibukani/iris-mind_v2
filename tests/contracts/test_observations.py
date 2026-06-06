"""Tests for Observations contracts."""
from __future__ import annotations

import pytest

from iris.contracts.observations import ObservationContext
from iris.core.ids import AccountId


def test_observation_context_metadata_is_defensively_copied() -> None:
    """ObservationContext defensively copies metadata."""
    metadata = {"mood": "happy"}
    context = ObservationContext(
        account_id=AccountId("acc-1"),
        metadata=metadata,
    )

    metadata["mood"] = "sad"

    assert context.metadata["mood"] == "happy"
    with pytest.raises(TypeError):
        context.metadata["new"] = "value"  # type: ignore[index]  # testing immutability
