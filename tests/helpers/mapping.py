"""Mapping immutability assertions that do not require suppression comments."""

from __future__ import annotations

import operator
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Mapping


def assert_mapping_rejects_item_assignment(mapping: Mapping[str, str]) -> None:
    """Assert a mapping rejects item assignment at runtime."""
    with pytest.raises(TypeError):
        operator.setitem(mapping, "new", "value")
