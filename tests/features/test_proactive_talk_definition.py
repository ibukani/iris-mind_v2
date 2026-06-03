"""Tests for proactive talk feature definition and observation contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

import pytest

from iris.contracts.observations import IdleTickObservation, ObservationKind
from iris.core.ids import ObservationId, SessionId
from iris.features.definition import FeatureDefinition
from iris.features.proactive_talk import define_proactive_talk_feature


def test_proactive_talk_feature_definition_is_explicit_and_provider_neutral() -> None:
    """Verify the proactive_talk feature definition is explicit and provider-neutral."""
    feature = define_proactive_talk_feature()

    assert isinstance(feature, FeatureDefinition)
    assert feature.name == "proactive_talk"
    assert [step.name for step in feature.pipeline_steps] == [
        "proactive_policy",
        "proactive_action_selection",
    ]
    assert feature.observation_sources == ()
    assert feature.background_jobs == ()


def test_idle_tick_observation_is_typed_and_provider_neutral() -> None:
    """Verify IdleTickObservation is a frozen dataclass and provider-neutral."""
    observation = IdleTickObservation(
        observation_id=ObservationId("obs-idle"),
        session_id=SessionId("session-idle"),
        actor=None,
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.IDLE_TICK,
        reason="quiet_room",
        idle_seconds=120.0,
    )

    assert observation.reason == "quiet_room"
    assert observation.idle_seconds == pytest.approx(120.0)

    with pytest.raises(FrozenInstanceError):
        observation.idle_seconds = 0.0


def test_proactive_talk_feature_no_forbidden_imports() -> None:
    """Verify proactive_talk feature files do not import deleted packages."""
    feature_dir = Path("iris/features/proactive_talk")
    source = "\n".join(path.read_text(encoding="utf-8") for path in feature_dir.glob("*.py"))

    assert "iris.agency" not in source
    assert "iris.event" not in source
    assert "iris.kernel.plugin" not in source
    assert "InternalBus" not in source
