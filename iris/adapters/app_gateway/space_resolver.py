"""SpaceBinding-aware SpaceResolver implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.adapters.app_gateway.ports import SpaceResolver
from iris.adapters.app_gateway.stable_ids import stable_space_id
from iris.contracts.spaces import InteractionSpace

if TYPE_CHECKING:
    from iris.contracts.external_refs import ExternalSpaceRef


class EphemeralSpaceResolver(SpaceResolver):
    """Space resolver that generates deterministic spaces without persistence."""

    @override
    async def resolve_space(
        self,
        space_ref: ExternalSpaceRef,
    ) -> InteractionSpace:
        """Return InteractionSpace with a stable SpaceId from provider/provider_space_ref.

        Returns:
            InteractionSpace: Deterministically resolved ephemeral space.
        """
        space_id = stable_space_id(space_ref.provider, space_ref.provider_space_ref)
        return InteractionSpace(
            space_id=space_id,
            space_kind=space_ref.space_kind,
            display_name=space_ref.display_name,
            metadata=dict(space_ref.metadata),
        )
