"""Tests for Observations contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from iris.contracts.observations import ObservationContext
from iris.core.ids import AccountId

if TYPE_CHECKING:
    from collections.abc import MutableMapping


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
        cast("MutableMapping[str, str]", context.metadata)["new"] = "value"
