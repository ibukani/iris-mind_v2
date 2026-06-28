"""Shared metadata for runtime model slots."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSlotSpec:
    """Shared metadata for one runtime model slot."""

    name: str
    default_max_output_tokens: int


_MODEL_SLOT_SPECS: tuple[ModelSlotSpec, ...] = (
    ModelSlotSpec("default_chat", 512),
    ModelSlotSpec("fast_judge", 128),
    ModelSlotSpec("reasoning", 1024),
)


def model_slot_specs() -> tuple[ModelSlotSpec, ...]:
    """Return the canonical runtime model slot metadata.

    Returns:
        Shared metadata in default_chat / fast_judge / reasoning order.
    """
    return _MODEL_SLOT_SPECS
