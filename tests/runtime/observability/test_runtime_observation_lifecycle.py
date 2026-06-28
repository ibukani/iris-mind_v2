"""Runtime observation lifecycle observer tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, override

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.contracts.actions import PresentedOutput
from iris.contracts.activity import ActivityKind
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActivityEventObservation,
    ActorMessageObservation,
    Observation,
    ObservationContext,
    ObservationKind,
    PresenceSignalObservation,
)
from iris.contracts.presence import PresenceStatus
from iris.core.ids import ActorId, CorrelationId, ObservationId, SessionId, SpaceId
from iris.runtime.app import IrisApp
from iris.runtime.ingress.observation_ingress import (
    ObservationCapability,
    ObservationIngressContext,
    unauthenticated_external_ingress,
)
from iris.runtime.service import IrisRuntimeService, ObservationEnvelope
from iris.runtime.wiring.app import wire_default_app

if TYPE_CHECKING:
    from iris.contracts.workspace_context import SituationContextSnapshot


class _RecordingObserver:
    """Runtime observation observer fake."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def record(self, event: str, **fields: object) -> None:
        self.events.append((event, fields))


class _ReactionHandler:
    """Activity event reaction handler fake."""

    async def handle(
        self,
        observation: ActivityEventObservation,
        situation_context: SituationContextSnapshot | None,
        ingress: ObservationIngressContext,
    ) -> PresentedOutput:
        """Return a deterministic reaction output."""
        del observation, situation_context, ingress
        return PresentedOutput(text="reaction")


class _FailingApp(IrisApp):
    """IrisApp fake that always raises."""

    @override
    async def process_observation(
        self,
        observation: Observation,
        *,
        situation_context: SituationContextSnapshot | None = None,
    ) -> PresentedOutput:
        """Raise deterministic error.

        Raises:
            _RuntimeTestError: Always raised by this fake app.
        """
        del observation, situation_context
        raise _RuntimeTestError(_RUNTIME_ERROR_MESSAGE)


class _RuntimeTestError(RuntimeError):
    """Runtime test error."""


_RUNTIME_ERROR_MESSAGE = "prompt text must not be logged"


def _context() -> ObservationContext:
    return ObservationContext(
        actor=Identity(
            actor_id=ActorId("actor-1"),
            actor_kind=ActorKind.HUMAN,
            display_name="Ada",
        ),
        space_id=SpaceId("space-1"),
    )


def _actor_message(text: str = "secret user text") -> ActorMessageObservation:
    return ActorMessageObservation(
        observation_id=ObservationId("obs-1"),
        session_id=SessionId("session-1"),
        context=_context(),
        occurred_at=datetime(2025, 1, 1, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )


def _presence_signal() -> PresenceSignalObservation:
    return PresenceSignalObservation(
        observation_id=ObservationId("obs-presence"),
        session_id=SessionId("session-1"),
        context=_context(),
        occurred_at=datetime(2025, 1, 1, tzinfo=UTC),
        kind=ObservationKind.PRESENCE_SIGNAL,
        status=PresenceStatus.ONLINE,
    )


def _activity_event() -> ActivityEventObservation:
    return ActivityEventObservation(
        observation_id=ObservationId("obs-activity"),
        session_id=SessionId("session-1"),
        context=_context(),
        occurred_at=datetime(2025, 1, 1, tzinfo=UTC),
        kind=ObservationKind.ACTIVITY_EVENT,
        activity_kind=ActivityKind.ACTOR_TYPING_STARTED,
    )


def _event_names(observer: _RecordingObserver) -> list[str]:
    return [event for event, _ in observer.events]


@pytest.mark.anyio
async def test_actor_message_path_emits_lifecycle_events() -> None:
    """Actor message emits integration, context, route, cognitive, success events."""
    observer = _RecordingObserver()
    app = wire_default_app(FakeLLMClient(responses=("ok",)))
    service = IrisRuntimeService(app, observation_observer=observer)

    await service.handle_observation(
        ObservationEnvelope.external_client(
            observation=_actor_message(),
            correlation_id=CorrelationId("corr-1"),
        ),
    )

    assert _event_names(observer) == [
        "runtime.observation.start",
        "runtime.observation.integrate.start",
        "runtime.observation.integrate.success",
        "runtime.context.assemble.start",
        "runtime.context.assemble.success",
        "runtime.observation.route",
        "runtime.cognitive.start",
        "runtime.cognitive.success",
        "runtime.observation.success",
    ]
    assert all(fields["correlation_id"] == "corr-1" for _, fields in observer.events)


@pytest.mark.anyio
async def test_presence_signal_path_emits_no_send_without_cognitive() -> None:
    """Presence signal emits no_send and does not enter cognitive processing."""
    observer = _RecordingObserver()
    service = IrisRuntimeService(
        wire_default_app(FakeLLMClient()),
        observation_observer=observer,
    )

    await service.handle_observation(
        ObservationEnvelope.external_client(
            observation=_presence_signal(),
            correlation_id=CorrelationId("corr-1"),
        ),
    )

    assert "runtime.observation.no_send" in _event_names(observer)
    assert "runtime.cognitive.start" not in _event_names(observer)


@pytest.mark.anyio
async def test_activity_event_path_emits_activity_reaction_events() -> None:
    """Activity event path emits activity reaction lifecycle events."""
    observer = _RecordingObserver()
    service = IrisRuntimeService(
        wire_default_app(FakeLLMClient()),
        activity_event_reaction_handler=_ReactionHandler(),
        observation_observer=observer,
    )

    await service.handle_observation(
        ObservationEnvelope.trusted_adapter(
            observation=_activity_event(),
            adapter_id="adapter-1",
            provider="discord",
            capabilities=frozenset({ObservationCapability.REACT_TO_ACTIVITY}),
            correlation_id=CorrelationId("corr-1"),
        ),
    )

    assert "runtime.activity_reaction.start" in _event_names(observer)
    assert "runtime.activity_reaction.success" in _event_names(observer)


@pytest.mark.anyio
async def test_exception_path_emits_error_and_reraises() -> None:
    """Runtime observation errors are observed and re-raised."""
    observer = _RecordingObserver()
    service = IrisRuntimeService(_FailingApp(steps=()), observation_observer=observer)

    with pytest.raises(_RuntimeTestError, match="prompt text"):
        await service.handle_observation(
            ObservationEnvelope(
                observation=_actor_message(),
                ingress=unauthenticated_external_ingress(),
                correlation_id=CorrelationId("corr-1"),
            ),
        )

    assert _event_names(observer)[-1] == "runtime.observation.error"
    assert observer.events[-1][1]["error_type"] == "_RuntimeTestError"


@pytest.mark.anyio
async def test_lifecycle_fields_do_not_include_user_or_prompt_text() -> None:
    """Lifecycle event fields do not include user text or prompt text."""
    observer = _RecordingObserver()
    app = wire_default_app(FakeLLMClient(responses=("ok",)))
    service = IrisRuntimeService(app, observation_observer=observer)

    await service.handle_observation(
        ObservationEnvelope.external_client(
            observation=_actor_message("very secret user text"),
            correlation_id=CorrelationId("corr-1"),
        ),
    )

    rendered = repr(observer.events)
    assert "very secret user text" not in rendered
    assert "prompt" not in rendered
