"""Account contract tests."""

from __future__ import annotations

from iris.contracts.accounts import AccountProfile
from iris.core.ids import AccountId, ActorId, ExternalRef
from tests.helpers.immutability import assert_frozen_field


def test_account_profile_stores_provider_identity() -> None:
    """AccountProfile stores account/provider identity."""
    profile = AccountProfile(
        account_id=AccountId("account-1"),
        provider="discord",
        provider_subject=ExternalRef("discord-user-1"),
        display_name="Mina",
        linked_actor_id=ActorId("actor-1"),
        metadata={"region": "jp"},
    )

    assert profile.account_id == AccountId("account-1")
    assert profile.provider == "discord"
    assert profile.provider_subject == ExternalRef("discord-user-1")
    assert profile.linked_actor_id == ActorId("actor-1")
    assert profile.metadata["region"] == "jp"


def test_account_profile_is_frozen() -> None:
    """AccountProfile is immutable."""
    profile = AccountProfile(
        account_id=AccountId("account-1"),
        provider="discord",
        provider_subject=ExternalRef("discord-user-1"),
        display_name="Mina",
    )

    assert_frozen_field(profile, "display_name", "Renamed")
