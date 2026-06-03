from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.contracts.observations import IdleTickObservation, ObservationKind
from iris.core.ids import ObservationId, SessionId
from iris.features.definition import FeatureDefinition
from iris.runtime.wiring.features import (
    wire_proactive_talk_cognitive_cycle,
    wire_proactive_talk_feature,
)


def test_wire_proactive_talk_feature_returns_explicit_feature_definition() -> None:
    feature = wire_proactive_talk_feature()

    assert isinstance(feature, FeatureDefinition)
    assert feature.name == "proactive_talk"
    assert feature.observation_sources == ()
    assert feature.background_jobs == ()


@pytest.mark.anyio
async def test_wire_proactive_talk_cognitive_cycle_composes_feature_steps() -> None:
    cycle = wire_proactive_talk_cognitive_cycle()
    result = await cycle.run(
        IdleTickObservation(
            observation_id=ObservationId("obs-proactive-wiring"),
            session_id=SessionId("session-proactive-wiring"),
            actor=None,
            occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
            kind=ObservationKind.IDLE_TICK,
            idle_seconds=600.0,
        )
    )

    assert result.selected_plan.turn_intent == "proactive_talk"
    assert result.selected_plan.should_respond is True
