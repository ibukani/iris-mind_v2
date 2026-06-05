"""SpaceBinding-aware SpaceResolver implementation."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, override

from iris.adapters.app_gateway.ports import SpaceResolver
from iris.contracts.spaces import InteractionSpace, SpaceParticipant, SpaceParticipantKind
from iris.core.ids import SpaceId

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from iris.adapters.app_gateway.ports import SpaceBindingStore
    from iris.contracts.identity import Identity
    from iris.contracts.spaces import SpaceKind
    from iris.core.ids import ExternalRef


class SpaceBindingAwareSpaceResolver(SpaceResolver):
    """SpaceResolver that uses SpaceBindingStore to map external spaces."""

    def __init__(self, *, binding_store: SpaceBindingStore | None = None) -> None:
        """Initialize with an optional binding store."""
        self._binding_store = binding_store

    @override
    async def resolve_space(
        self,
        *,
        provider: str,
        provider_space_ref: ExternalRef,
        display_name: str,
        space_kind: SpaceKind,
        participants: Sequence[Identity] = (),
        metadata: Mapping[str, str] | None = None,
    ) -> InteractionSpace:
        """Resolve external space ref to an InteractionSpace.

        Returns:
            InteractionSpace: The resolved space.
        """
        space_metadata = dict(metadata) if metadata else {}
        space_participants = tuple(
            SpaceParticipant(
                actor_id=p.actor_id,
                participant_kind=SpaceParticipantKind(p.actor_kind.value),
                display_name=p.display_name,
                identity=p,
                metadata=p.metadata,
            )
            for p in participants
        )

        if self._binding_store is not None:
            binding = await self._binding_store.get_by_external_ref(
                provider=provider,
                provider_space_ref=provider_space_ref,
            )
            if binding is not None:
                # Merge metadata, preferring binding metadata if keys collide
                merged_metadata = {**space_metadata, **binding.metadata}
                return InteractionSpace(
                    space_id=binding.space_id,
                    space_kind=binding.space_kind,
                    display_name=binding.display_name,
                    participants=space_participants,
                    metadata=merged_metadata,
                )

        # Fallback: deterministic non-persistent space_id
        hash_input = f"{provider}:{provider_space_ref}".encode()
        deterministic_hash = hashlib.sha256(hash_input).hexdigest()[:16]
        fallback_space_id = SpaceId(f"space-{provider}-{deterministic_hash}")

        return InteractionSpace(
            space_id=fallback_space_id,
            space_kind=space_kind,
            display_name=display_name,
            participants=space_participants,
            metadata=space_metadata,
        )
