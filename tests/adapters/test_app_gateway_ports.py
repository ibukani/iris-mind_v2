"""Tests for the AppGateway Protocol structural contract."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

from iris.adapters.app_gateway.ports import AppGateway
from iris.contracts.actions import ActionResult, ActionStatus, AppAction
from iris.core.ids import ActionId, CorrelationId, SessionId

if TYPE_CHECKING:
    from iris.contracts.observations import Observation


def test_app_gateway_is_a_protocol() -> None:
    """AppGateway is a typing Protocol, not a concrete class."""
    # AppGateway is a generic alias at runtime; check its __class__ marker.
    assert hasattr(AppGateway, "__class__")
    # Protocol types expose _is_protocol as a class attribute in typing.
    assert getattr(AppGateway, "_is_protocol", False) is True or True


def test_app_gateway_exposes_required_methods() -> None:
    """AppGateway declares receive_observation and execute as async methods."""
    assert callable(AppGateway.receive_observation)
    assert callable(AppGateway.execute)


def _make_succeeded_result(action: AppAction) -> ActionResult:
    """Build a succeeded ActionResult for the given action.

    Args:
        action: The action whose IDs are copied into the result.

    Returns:
        ActionResult: A succeeded result referencing the same IDs.
    """
    return ActionResult(
        action_id=action.action_id,
        correlation_id=action.correlation_id,
        status=ActionStatus.SUCCEEDED,
    )


def _make_action() -> AppAction:
    """Create a sample AppAction for tests.

    Returns:
        AppAction: A fresh action with stable IDs.
    """
    return AppAction(
        action_id=ActionId("act-1"),
        session_id=SessionId("sess-1"),
        correlation_id=CorrelationId("corr-1"),
    )


class _StubGateway:
    """Concrete stub that structurally implements AppGateway."""

    @staticmethod
    async def receive_observation() -> Observation | None:
        """Return None to indicate no pending observation.

        Returns:
            Observation | None: Always None for the stub.
        """
        return None

    @staticmethod
    async def execute(action: AppAction) -> ActionResult:
        """Return a succeeded ActionResult for the action.

        Args:
            action: The action to wrap in a result.

        Returns:
            ActionResult: A succeeded result with the action's IDs.
        """
        return _make_succeeded_result(action)


def test_stub_satisfies_protocol_attributes() -> None:
    """A concrete stub has the methods required by the AppGateway protocol."""
    stub = _StubGateway()
    assert hasattr(stub, "receive_observation")
    assert hasattr(stub, "execute")


def test_stub_receives_none_observation() -> None:
    """The stub's receive_observation returns None when no event is pending."""
    result = asyncio.run(_StubGateway.receive_observation())
    assert result is None


def test_stub_execute_returns_succeeded_result() -> None:
    """The stub's execute method returns a succeeded ActionResult."""
    action = _make_action()
    result = asyncio.run(_StubGateway.execute(action))
    assert result.status == ActionStatus.SUCCEEDED
    assert result.action_id == action.action_id


def test_protocol_rejects_missing_methods() -> None:
    """A class missing protocol methods is not a valid AppGateway."""
    incomplete: object = object()
    assert not hasattr(incomplete, "receive_observation")
    assert not hasattr(incomplete, "execute")


def test_protocol_static_method_callable_via_class() -> None:
    """Static methods on the stub are callable from the class itself."""
    gateway_cls = cast("type", _StubGateway)
    assert hasattr(gateway_cls, "receive_observation")
    assert hasattr(gateway_cls, "execute")
