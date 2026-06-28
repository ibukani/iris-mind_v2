"""Tests for feature definition and metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.features.definition import ActivityReactionPlanner, FeatureDefinition
from iris.features.proactive_talk import define_proactive_talk_feature
from iris.runtime.wiring.features import collect_cognitive_steps, wire_runtime_features

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


def test_runtime_features_register_event_reaction_through_feature_definition() -> None:
    """標準 composition root は event reaction を FeatureDefinition として登録する。"""
    catalog = wire_runtime_features()

    assert tuple(feature.name for feature in catalog.features) == ("basic_action", "event_reaction")
    event_reaction_feature = next(f for f in catalog.features if f.name == "event_reaction")
    assert len(event_reaction_feature.activity_reaction_planners) == 1


def test_collect_cognitive_steps_preserves_feature_registration_order() -> None:
    """認知ステップはフィーチャー登録順とフィーチャー内順序を維持する。"""
    proactive_steps = define_proactive_talk_feature().cognitive_steps
    features = (
        FeatureDefinition(name="first", cognitive_steps=proactive_steps[:1]),
        FeatureDefinition(name="second", cognitive_steps=proactive_steps[1:]),
    )

    assert collect_cognitive_steps(features) == tuple(proactive_steps)
