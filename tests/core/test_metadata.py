"""Tests for core metadata helpers."""
from __future__ import annotations

from types import MappingProxyType

import pytest

from iris.core.metadata import EMPTY_METADATA, immutable_metadata


def test_immutable_metadata_returns_empty_when_none() -> None:
    """immutable_metadata returns EMPTY_METADATA when given None."""
    assert immutable_metadata(None) is EMPTY_METADATA


def test_immutable_metadata_returns_same_proxy_if_already_proxy() -> None:
    """immutable_metadata returns the same object if already a MappingProxyType."""
    proxy = MappingProxyType[str, str]({"key": "value"})
    assert immutable_metadata(proxy) is proxy


def test_immutable_metadata_copies_dict_into_proxy() -> None:
    """immutable_metadata creates an immutable copy of a dictionary."""
    mutable_dict = {"source": "discord"}
    result = immutable_metadata(mutable_dict)

    assert isinstance(result, MappingProxyType)
    assert result == {"source": "discord"}

    mutable_dict["source"] = "changed"
    assert result["source"] == "discord"

    with pytest.raises(TypeError):
        result["new"] = "value"  # type: ignore[index]  # testing immutability
