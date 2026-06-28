"""Tests for feature definition and metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.features.definition import ActivityReactionPlanner, FeatureDefinition
from iris.runtime.wiring.features import wire_runtime_extensions

if TYPE_CHECKING:
    from iris.contracts.availability import AvailabilitySnapshot
    from iris.contracts.event_reaction import EventReactionDecision
    from iris.contracts.observations import ActivityEventObservation


def test_feature_definition_defaults_are_empty_tuples() -> None:
    """Feature definition lists should default to empty tuples."""
    feature = FeatureDefinition(name="empty")
    assert feature.name == "empty"
    assert feature.cognitive_steps == ()
    assert feature.activity_reaction_planners == ()
    assert feature.observation_sources == ()
    assert feature.learning_hooks == ()
    assert feature.background_jobs == ()


def test_feature_definition_can_attach_activity_reaction_planner() -> None:
    """Activity reaction planners can be attached to feature definitions."""

    class DummyPlanner(ActivityReactionPlanner):
        @override
        def plan(
            self,
            observation: ActivityEventObservation,
            *,
            availability: AvailabilitySnapshot | None,
        ) -> EventReactionDecision:
            del observation, availability
            raise NotImplementedError

    feature = FeatureDefinition(
        name="test_reaction",
        activity_reaction_planners=(DummyPlanner(),),
    )
    assert len(feature.activity_reaction_planners) == 1
    assert isinstance(feature.activity_reaction_planners[0], DummyPlanner)


def test_runtime_extensions_register_event_reaction_through_feature_definition() -> None:
    """標準 composition root は event reaction を FeatureDefinition として登録する。"""
    composition = wire_runtime_extensions()

    assert tuple(feature.name for feature in composition.features) == ("event_reaction",)
    assert len(composition.features[0].activity_reaction_planners) == 1
