"""Tests for the Iris custom exception hierarchy."""

from __future__ import annotations

import pytest

from iris.errors import (
    IrisCapabilityError,
    IrisConfigError,
    IrisConnectionError,
    IrisError,
    IrisLLMError,
    IrisLLMUnavailableError,
    IrisMemoryError,
    IrisRuntimeError,
    IrisSessionError,
    IrisToolError,
)


def test_iris_error_default_code_uses_class_name() -> None:
    """Without an explicit code, code defaults to the class name."""
    error = IrisError("boom")
    assert error.message == "boom"
    assert error.code == "IrisError"
    assert str(error) == "boom"


def test_iris_error_with_explicit_code_includes_prefix() -> None:
    """An explicit code is prefixed in the string form."""
    error = IrisError("boom", code="E_BOOM")
    assert error.code == "E_BOOM"
    assert str(error) == "[E_BOOM] boom"


def test_iris_error_is_exception() -> None:
    """IrisError can be raised and caught as an Exception subclass.

    Raises:
        IrisConfigError: The test raises this to verify the hierarchy.
    """
    message = "bad"
    with pytest.raises(IrisError) as exc:
        raise IrisConfigError(message)
    assert exc.value.message == "bad"
    assert exc.value.code == "IrisConfigError"


@pytest.mark.parametrize(
    "exc_cls",
    [
        IrisConfigError,
        IrisRuntimeError,
        IrisConnectionError,
        IrisMemoryError,
        IrisToolError,
        IrisSessionError,
    ],
)
def test_subclass_inherits_iris_error(exc_cls: type[IrisError]) -> None:
    """Subclasses extend IrisError and inherit its constructor.

    Args:
        exc_cls: Concrete IrisError subclass under test.
    """
    error = exc_cls("oops", code="E_X")
    assert isinstance(error, IrisError)
    assert error.message == "oops"
    assert error.code == "E_X"
    assert str(error) == "[E_X] oops"


def test_iris_llm_error_inherits_connection_error() -> None:
    """LLM errors are a kind of connection error."""
    error = IrisLLMError("rate limited")
    assert isinstance(error, IrisConnectionError)
    assert isinstance(error, IrisError)
    assert str(error) == "rate limited"


def test_iris_llm_unavailable_error_inherits_llm_error() -> None:
    """Unavailable LLM errors extend the generic LLM error."""
    error = IrisLLMUnavailableError("no key")
    assert isinstance(error, IrisLLMError)
    assert isinstance(error, IrisConnectionError)
    assert str(error) == "no key"


def test_iris_capability_error_inherits_tool_error() -> None:
    """Capability errors extend the tool error family."""
    error = IrisCapabilityError("missing tool")
    assert isinstance(error, IrisToolError)
    assert isinstance(error, IrisError)
    assert str(error) == "missing tool"
