"""Tests for feature definition and metadata."""

from __future__ import annotations

from iris.features.definition import FeatureDefinition, ActivityReactionPlanner


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
        def plan(self, observation, *, availability):
            raise NotImplementedError
            
    feature = FeatureDefinition(
        name="test_reaction",
        activity_reaction_planners=(DummyPlanner(),),
    )
    assert len(feature.activity_reaction_planners) == 1
    assert isinstance(feature.activity_reaction_planners[0], DummyPlanner)
