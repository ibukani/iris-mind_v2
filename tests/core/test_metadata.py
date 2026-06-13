"""Tests for core metadata helpers."""

from __future__ import annotations

from types import MappingProxyType

from iris.core.metadata import EMPTY_METADATA, immutable_metadata
from tests.helpers.mapping import assert_mapping_rejects_item_assignment


def test_immutable_metadata_returns_empty_when_none() -> None:
    """immutable_metadata returns EMPTY_METADATA when given None."""
    assert immutable_metadata(None) is EMPTY_METADATA


def test_immutable_metadata_returns_same_proxy_only_if_empty_metadata() -> None:
    """immutable_metadata returns the same object only if it is EMPTY_METADATA."""
    assert immutable_metadata(EMPTY_METADATA) is EMPTY_METADATA


def test_immutable_metadata_copies_existing_proxy_to_prevent_view_mutations() -> None:
    """immutable_metadata creates a new copy even if given a MappingProxyType."""
    mutable_dict = {"key": "value"}
    proxy = MappingProxyType[str, str](mutable_dict)

    result = immutable_metadata(proxy)
    assert result is not proxy
    assert result == {"key": "value"}

    # Mutate the original dict, the returned proxy should be unaffected
    mutable_dict["key"] = "mutated"
    assert result["key"] == "value"


def test_immutable_metadata_copies_dict_into_proxy() -> None:
    """immutable_metadata creates an immutable copy of a dictionary."""
    mutable_dict = {"source": "discord"}
    result = immutable_metadata(mutable_dict)

    assert isinstance(result, MappingProxyType)
    assert result == {"source": "discord"}

    mutable_dict["source"] = "changed"
    assert result["source"] == "discord"

    assert_mapping_rejects_item_assignment(result)
