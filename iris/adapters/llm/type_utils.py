"""LLM adapter type utility functions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeGuard


def is_object_sequence(value: object) -> TypeGuard[list[object] | tuple[object, ...]]:
    """Narrow sequence types for iteration.

    Runtime check uses isinstance against the base sequence types. Type
    parameters cannot be verified at runtime, so the narrowed type assumes
    ``object`` element type which is the widest compatible type.

    Returns:
        True if value is a list or tuple, narrowing to the widened type.
    """
    return isinstance(value, (list, tuple))


def is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    """Narrow mapping types for item iteration.

    Runtime check uses isinstance against Mapping; type parameters are erased
    at runtime so the narrowed type uses the widest compatible parameter types.

    Returns:
        True if value is a Mapping, narrowing to the widened type.
    """
    return isinstance(value, Mapping)
