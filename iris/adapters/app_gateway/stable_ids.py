"""Shared deterministic stable ID helpers for AppGateway."""

from __future__ import annotations

import hashlib
from hashlib import blake2b

from iris.core.ids import AccountId, ActorId, ExternalRef, SpaceId


def stable_external_id(prefix: str, provider: str, external_ref: str) -> str:
    """Generate a short deterministic ID string for resolvers.

    Args:
        prefix: Prefix for the ID (e.g., "actor", "account", "space").
        provider: The provider name.
        external_ref: The external reference from the provider.

    Returns:
        str: A deterministic short ID string.
    """
    digest = blake2b(
        f"{provider}:{external_ref}".encode(),
        digest_size=12,
    ).hexdigest()
    return f"{prefix}-{provider}-{digest}"


def stable_account_id(provider: str, provider_subject: ExternalRef | str) -> AccountId:
    """Generate a stable AccountId.

    Args:
        provider: The provider name.
        provider_subject: The provider subject reference.

    Returns:
        AccountId: The stable account ID.
    """
    return AccountId(stable_external_id("account", provider, str(provider_subject)))


def stable_actor_id(account_id: AccountId) -> ActorId:
    """Generate a stable ActorId.

    Args:
        account_id: The resolved account ID.

    Returns:
        ActorId: The stable actor ID.
    """
    return ActorId(stable_external_id("actor", "", str(account_id)))


def stable_space_id(provider: str, provider_space_ref: ExternalRef | str) -> SpaceId:
    """Generate a stable SpaceId.

    Maintains legacy sha256 format for space fallback compatibility.

    Args:
        provider: The provider name.
        provider_space_ref: The provider space reference.

    Returns:
        SpaceId: The stable space ID.
    """
    digest = hashlib.sha256(f"{provider}:{provider_space_ref}".encode()).hexdigest()[:16]
    return SpaceId(f"space-{provider}-{digest}")
