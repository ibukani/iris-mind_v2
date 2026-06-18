"""Contract tests for the gRPC ingress error taxonomy.

These tests pin down the public surface of
:mod:`iris.adapters.grpc.errors`, which is referenced by the servicer
to make the narrow-exception fallback policy auditable.
"""

from __future__ import annotations

from typing import override

import pytest

from iris.adapters.grpc.errors import IngressError


def test_ingress_error_is_an_exception_subclass() -> None:
    """``IngressError`` is catchable as a regular ``Exception`` subclass.

    Raises:
        IngressError: Always raised by the test body.
    """
    message = "boom"
    with pytest.raises(IngressError):
        raise IngressError(message)


def test_ingress_error_can_be_caught_by_exception_handler() -> None:
    """``IngressError`` instances are also ``Exception`` instances."""
    exc = IngressError("boom")
    assert isinstance(exc, Exception)


def test_ingress_error_message_round_trips() -> None:
    """The error message is preserved when raised and re-read.

    Raises:
        IngressError: Always raised by the test body.
    """
    message = "narrow ingress error"
    with pytest.raises(IngressError) as excinfo:
        raise IngressError(message)
    assert str(excinfo.value) == message


def test_ingress_error_supports_subclassing() -> None:
    """Downstream ingress-specific exceptions can subclass ``IngressError``."""

    class _SpecificIngressError(IngressError):
        """A concrete ingress error used to verify subclassing works."""

        @override
        def __init__(self, code: str) -> None:
            """Create a specific ingress error with a stable code."""
            super().__init__(f"ingress error: {code}")
            self.code = code

    exc = _SpecificIngressError("timeout")
    assert isinstance(exc, IngressError)
    assert exc.code == "timeout"
    assert str(exc) == "ingress error: timeout"
