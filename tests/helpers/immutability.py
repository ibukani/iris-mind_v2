"""Helpers for testing immutable contract values without suppressions."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

from pydantic import ValidationError
import pytest


def assert_frozen_field(instance: object, field_name: str, value: object) -> None:
    """Assert that a frozen dataclass field rejects runtime mutation.

    Args:
        instance: Frozen dataclass-like object under test.
        field_name: Field name to mutate through the runtime setattr path.
        value: Replacement value attempted by the test.
    """
    with pytest.raises((FrozenInstanceError, ValidationError)):
        setattr(instance, field_name, value)
