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
from iris.runtime.activity.integrator import ActivityIntegrator
from iris.runtime.activity.store import InMemoryActivityStore
from iris.runtime.app import IrisApp
from iris.runtime.observations.trust import ObservationTrustPolicy
from iris.runtime.presence.integrator import PresenceIntegrator
from iris.runtime.presence.store import InMemoryPresenceStore
from iris.runtime.service import IrisRuntimeService, ObservationEnvelope
from iris.runtime.spaces.occupancy_integrator import SpaceOccupancyIntegrator
from iris.runtime.spaces.occupancy_store import InMemorySpaceOccupancyStore

if TYPE_CHECKING:
    from iris.cognitive.cycle.models import ActionSelectionResult
    from iris.cognitive.workspace.frame import WorkspaceFrame

_OCCURRED_AT = datetime(2026, 6, 13, tzinfo=UTC)
_RECEIVED_AT = _OCCURRED_AT + timedelta(seconds=1)


@pytest.mark.anyio
async def test_runtime_service_integrates_activity_without_cognitive_response() -> None:
    """activityをstoreへ統合し、sendable outputを生成しないことを確認する。"""
    activity_store = InMemoryActivityStore()
    occupancy_store = InMemorySpaceOccupancyStore()
    service = _service(
        activity_store=activity_store,
        occupancy_store=occupancy_store,
    )

    response = await service.handle_observation(
        ObservationEnvelope(observation=_activity_observation())
    )

    assert not response.output.is_sendable
    assert await activity_store.latest_for_actor(ActorId("actor-1")) is not None
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

    response = await service.handle_observation(ObservationEnvelope(observation=_presence_signal()))

    assert not response.output.is_sendable
    assert (
        await presence_store.get_presence_for_actor(
            ActorId("actor-1"),
            now=_OCCURRED_AT,
        )
        is not None
    )


@pytest.mark.anyio
async def test_runtime_service_does_not_mutate_state_for_untrusted_claims() -> None:
    """Untrusted claimがstoreを更新せず、requestも失敗しないことを確認する。"""
    activity_store = InMemoryActivityStore()
    presence_store = InMemoryPresenceStore()
    service = _service(
        activity_store=activity_store,
        presence_store=presence_store,
    )

    activity_response = await service.handle_observation(
        ObservationEnvelope(observation=_activity_observation(source="untrusted"))
    )
    presence_response = await service.handle_observation(
        ObservationEnvelope(observation=_presence_signal(source="untrusted"))
    )

    assert not activity_response.output.is_sendable
    assert not presence_response.output.is_sendable
    assert await activity_store.latest_for_actor(ActorId("actor-1")) is None
    assert (
        await presence_store.get_presence_for_actor(
            ActorId("actor-1"),
            now=_OCCURRED_AT,
        )
        is None
    )


def _service(
    *,
    activity_store: InMemoryActivityStore | None = None,
    presence_store: InMemoryPresenceStore | None = None,
    occupancy_store: InMemorySpaceOccupancyStore | None = None,
) -> IrisRuntimeService:
    trust_policy = ObservationTrustPolicy(
        trusted_activity_sources=frozenset({"internal"}),
        trusted_presence_sources=frozenset({"internal"}),
    )
    return IrisRuntimeService(
        IrisApp(steps=(_UnexpectedCognitiveStep(),)),
        activity_integrator=(
            ActivityIntegrator(activity_store, trust_policy, _now)
            if activity_store is not None
            else None
        ),
        presence_integrator=(
            PresenceIntegrator(presence_store, trust_policy, _now)
            if presence_store is not None
            else None
        ),
        occupancy_integrator=(
            SpaceOccupancyIntegrator(occupancy_store, trust_policy, _now)
            if occupancy_store is not None
            else None
        ),
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
