"""Tests for Account contracts."""
from __future__ import annotations

import pytest

from iris.contracts.accounts import AccountProfile
from iris.core.ids import AccountId, ExternalRef


def test_account_profile_metadata_is_defensively_copied() -> None:
    """AccountProfile defensively copies metadata."""
    metadata = {"key": "value"}
    profile = AccountProfile(
        account_id=AccountId("acc-1"),
        provider="discord",
        provider_subject=ExternalRef("sub-1"),
        display_name="User",
        metadata=metadata,
    )

    metadata["key"] = "changed"

    assert profile.metadata["key"] == "value"
    with pytest.raises(TypeError):
        profile.metadata["new"] = "value"  # type: ignore[index]  # testing immutability
