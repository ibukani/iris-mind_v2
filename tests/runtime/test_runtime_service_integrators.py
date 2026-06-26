"""runtime service integrator tests。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from iris.contracts.activity import ActivityKind
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActivityEventObservation,
    ObservationContext,
    ObservationKind,
    PresenceSignalObservation,
)
from iris.contracts.presence import PresenceStatus
from iris.core.ids import ActorId, ObservationId, SessionId, SpaceId
from iris.runtime.app import IrisApp
from iris.runtime.ingress.observation_ingress import (
    ObservationCapability,
    ObservationIngressContext,
)
from iris.runtime.ingress.observation_trust import ObservationTrustPolicy
from iris.runtime.service import (
    IntegratingObservationPipeline,
    IrisRuntimeService,
    ObservationEnvelope,
)
from iris.runtime.state.activity_integrator import ActivityIntegrator
from iris.runtime.state.activity_journal import InMemoryActivityJournal
from iris.runtime.state.activity_projection import InMemoryActivityProjectionStore
from iris.runtime.state.presence import InMemoryPresenceStore
from iris.runtime.state.presence_integrator import PresenceIntegrator
from iris.runtime.state.space_occupancy import InMemorySpaceOccupancyStore
from iris.runtime.state.space_occupancy_integrator import SpaceOccupancyIntegrator

if TYPE_CHECKING:
    from iris.cognitive.cycle.models import ActionSelectionResult
    from iris.cognitive.workspace.frame import WorkspaceFrame
    from iris.runtime.ingress.observation_integrator import ObservationIntegrator

_OCCURRED_AT = datetime(2026, 6, 13, tzinfo=UTC)
_RECEIVED_AT = _OCCURRED_AT + timedelta(seconds=1)


@pytest.mark.anyio
async def test_runtime_service_integrates_activity_without_cognitive_response() -> None:
    """activityをstoreへ統合し、sendable outputを生成しないことを確認する。"""
    journal = InMemoryActivityJournal()
    projections = InMemoryActivityProjectionStore()
    occupancy_store = InMemorySpaceOccupancyStore()
    service = _service(
        journal=journal,
        projections=projections,
        occupancy_store=occupancy_store,
    )

    response = await service.handle_observation(
        ObservationEnvelope(
            observation=_activity_observation(),
            ingress=_ingress(
                ObservationCapability.INTEGRATE_ACTIVITY,
                ObservationCapability.UPDATE_SPACE_OCCUPANCY,
            ),
        )
    )

    assert not response.output.is_sendable
    assert await projections.latest_for_actor(ActorId("actor-1")) is not None
    occupancy = await occupancy_store.get_occupancy(
        SpaceId("space-1"),
        now=_RECEIVED_AT,
    )
    assert len(occupancy.occupants) == 1


@pytest.mark.anyio
async def test_runtime_service_integrates_presence_without_cognitive_response() -> None:
    """presenceをstoreへ統合し、sendable outputを生成しないことを確認する。"""
    presence_store = InMemoryPresenceStore()
    service = _service(presence_store=presence_store)

    response = await service.handle_observation(
        ObservationEnvelope(
            observation=_presence_signal(),
            ingress=_ingress(ObservationCapability.INTEGRATE_PRESENCE),
        )
    )

    assert not response.output.is_sendable
    assert (
        await presence_store.get_presence_for_actor(
            ActorId("actor-1"),
            now=_OCCURRED_AT,
        )
        is not None
    )


@pytest.mark.anyio
async def test_runtime_service_does_not_mutate_state_without_capabilities() -> None:
    """sourceやmetadataだけではstoreを更新せず、requestも失敗しない。"""
    journal = InMemoryActivityJournal()
    projections = InMemoryActivityProjectionStore()
    presence_store = InMemoryPresenceStore()
    service = _service(
        journal=journal,
        projections=projections,
        presence_store=presence_store,
    )

    activity_response = await service.handle_observation(
        ObservationEnvelope(
            observation=_activity_observation(source="discord_gateway"),
            ingress=_ingress(authenticated=False),
        )
    )
    presence_response = await service.handle_observation(
        ObservationEnvelope(
            observation=_presence_signal(source="internal"),
            ingress=_ingress(),
        )
    )

    assert not activity_response.output.is_sendable
    assert not presence_response.output.is_sendable
    assert await projections.latest_for_actor(ActorId("actor-1")) is None

    assert (
        await presence_store.get_presence_for_actor(
            ActorId("actor-1"),
            now=_OCCURRED_AT,
        )
        is None
    )


def _service(
    *,
    journal: InMemoryActivityJournal | None = None,
    projections: InMemoryActivityProjectionStore | None = None,
    presence_store: InMemoryPresenceStore | None = None,
    occupancy_store: InMemorySpaceOccupancyStore | None = None,
) -> IrisRuntimeService:
    trust_policy = ObservationTrustPolicy()
    integrators: list[ObservationIntegrator] = []
    if journal is not None and projections is not None:
        integrators.append(ActivityIntegrator(journal, projections, trust_policy, _now))
    if presence_store is not None:
        integrators.append(PresenceIntegrator(presence_store, trust_policy, _now))
    if occupancy_store is not None:
        integrators.append(SpaceOccupancyIntegrator(occupancy_store, trust_policy, _now))
    return IrisRuntimeService(
        IrisApp(steps=(_UnexpectedCognitiveStep(),)),
        observation_pipeline=IntegratingObservationPipeline(tuple(integrators)),
    )


def _activity_observation(
    *,
    source: str = "internal",
) -> ActivityEventObservation:
    return ActivityEventObservation(
        observation_id=ObservationId("obs-activity"),
        session_id=SessionId("session-1"),
        context=_context(source=source, include_space=True),
        occurred_at=_OCCURRED_AT,
        kind=ObservationKind.ACTIVITY_EVENT,
        activity_kind=ActivityKind.VOICE_JOINED,
    )


def _presence_signal(*, source: str = "internal") -> PresenceSignalObservation:
    return PresenceSignalObservation(
        observation_id=ObservationId("obs-presence"),
        session_id=SessionId("session-1"),
        context=_context(source=source),
        occurred_at=_OCCURRED_AT,
        kind=ObservationKind.PRESENCE_SIGNAL,
        status=PresenceStatus.ONLINE,
    )


def _context(*, source: str, include_space: bool = False) -> ObservationContext:
    return ObservationContext(
        actor=Identity(
            actor_id=ActorId("actor-1"),
            actor_kind=ActorKind.HUMAN,
            display_name="Actor",
        ),
        space_id=SpaceId("space-1") if include_space else None,
        source=source,
        metadata={"capability": "integrate_activity"},
    )


def _ingress(
    *capabilities: ObservationCapability,
    authenticated: bool = True,
) -> ObservationIngressContext:
    return ObservationIngressContext(
        adapter_id="trusted-adapter",
        provider="discord",
        authenticated=authenticated,
        capabilities=frozenset(capabilities),
    )


def _now() -> datetime:
    return _RECEIVED_AT


class _UnexpectedCognitiveStep:
    """state-only observationがcognitive cycleへ到達しないことを検証するstep。"""

    name = "unexpected"

    async def run(self, frame: WorkspaceFrame) -> ActionSelectionResult:
        """呼び出された場合にtestを失敗させる。

        Raises:
            AssertionError: state-only observationがcognitive cycleへ到達した場合。
        """
        msg = f"state-only observation reached cognitive cycle: {frame.observation.kind}"
        raise AssertionError(msg)
