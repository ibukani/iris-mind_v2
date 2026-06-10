"""In-memory SpaceBindingStore implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.adapters.app_gateway.ports import SpaceBindingStore
from iris.contracts.spaces import SpaceBindingStoreError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from iris.contracts.spaces import SpaceBinding
    from iris.core.ids import ExternalRef, SpaceId


class InMemorySpaceBindingStore(SpaceBindingStore):
    """In-memory storage for space bindings."""

    def __init__(self, bindings: Iterable[SpaceBinding] = ()) -> None:
        """Initialize the store with optional existing bindings."""
        self._bindings: dict[tuple[str, ExternalRef], SpaceBinding] = {}
        self._refs_by_space_id: dict[SpaceId, tuple[str, ExternalRef]] = {}
        for binding in bindings:
            self._put_sync(binding)

    def _put_sync(self, binding: SpaceBinding) -> SpaceBinding:
        key = (binding.provider, binding.provider_space_ref)
        existing_ref = self._refs_by_space_id.get(binding.space_id)
        if existing_ref is not None and existing_ref != key:
            msg = f"space_id conflict: {binding.space_id}"
            raise SpaceBindingStoreError(msg)

        existing = self._bindings.get(key)
        if existing is not None and existing.space_id != binding.space_id:
            self._refs_by_space_id.pop(existing.space_id, None)

        self._bindings[key] = binding
        self._refs_by_space_id[binding.space_id] = key
        return binding

    @override
    async def get_by_external_ref(
        self,
        *,
        provider: str,
        provider_space_ref: ExternalRef,
    ) -> SpaceBinding | None:
        """Get a space binding by provider and external space ref.

        Returns:
            SpaceBinding | None: The bound space or None.
        """
        key = (provider, provider_space_ref)
        return self._bindings.get(key)

    @override
    async def put(self, binding: SpaceBinding) -> SpaceBinding:
        """Create or update a space binding.

        Returns:
            SpaceBinding: Stored binding.
        """
        return self._put_sync(binding)
