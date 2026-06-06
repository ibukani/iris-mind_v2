"""Metadata immutability helper."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

EMPTY_METADATA: Mapping[str, str] = MappingProxyType[str, str]({})


def immutable_metadata(metadata: Mapping[str, str] | None = None) -> Mapping[str, str]:
    """Return an immutable defensive copy of metadata."""
    if metadata is None:
        return EMPTY_METADATA
    if isinstance(metadata, MappingProxyType):
        return metadata
    return MappingProxyType[str, str](dict[str, str](metadata))
