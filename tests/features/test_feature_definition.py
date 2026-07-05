"""Tests for feature definition and metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.contracts.actions import ActionPlan, PresentedOutput
from iris.features.definition import ActivityReactionPlanner, FeatureDefinition, FeatureKind
from iris.features.proactive_talk import define_proactive_talk_feature
from iris.runtime.wiring.features import (
    collect_action_plan_presenters,
    collect_background_loop_tasks,
    collect_cognitive_steps,
    collect_learning_hooks,
    collect_runtime_learning_hooks,
    wire_runtime_features,
)

if TYPE_CHECKING:
    from iris.contracts.availability import AvailabilitySnapshot
    from iris.contracts.event_reaction import EventReactionDecision
    from iris.contracts.learning import LearningEvent, RuntimeLearningEvent
    from iris.contracts.observations import ActivityEventObservation


def test_feature_definition_defaults_are_empty_tuples() -> None:
    """Feature definition lists should default to empty tuples."""
    feature = FeatureDefinition(name="empty")
    assert feature.name == "empty"
    assert feature.cognitive_steps == ()
    assert feature.activity_reaction_planners == ()
    assert feature.observation_sources == ()
    assert feature.learning_hooks == ()
    assert feature.runtime_learning_hooks == ()
    assert feature.background_loop_tasks == ()
    assert feature.kind is FeatureKind.COMPANION


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
    assert collect_learning_hooks(catalog.features) == ()


def test_collect_cognitive_steps_preserves_feature_registration_order() -> None:
    """認知ステップはフィーチャー登録順とフィーチャー内順序を維持する。"""
    proactive_steps = define_proactive_talk_feature().cognitive_steps
    features = (
        FeatureDefinition(name="first", cognitive_steps=proactive_steps[:1]),
        FeatureDefinition(name="second", cognitive_steps=proactive_steps[1:]),
    )

    assert collect_cognitive_steps(features) == tuple(proactive_steps)


def test_collect_action_plan_presenters_preserves_feature_registration_order() -> None:
    """Action plan presenters はフィーチャー登録順とフィーチャー内順序を維持する。"""

    class _Presenter:
        def can_present(self, plan: ActionPlan) -> bool:
            del plan
            return True

        async def present(self, plan: ActionPlan) -> PresentedOutput:
            del plan
            return PresentedOutput(text="ok")

    first = _Presenter()
    second = _Presenter()
    features = (
        FeatureDefinition(name="first", action_plan_presenters=(first,)),
        FeatureDefinition(name="second", action_plan_presenters=(second,)),
    )

    presenters = collect_action_plan_presenters(features)
    assert len(presenters) == 2
    assert presenters[0] is first
    assert presenters[1] is second


def test_learning_collectors_preserve_feature_registration_order() -> None:
    """Learning hooks と background loop tasks は feature 登録順を維持する。"""

    class _Hook:
        async def after_action_result(self, event: LearningEvent) -> None:
            _ = event

    class _RuntimeHook:
        async def after_runtime_event(self, event: RuntimeLearningEvent) -> None:
            _ = event

    class _Job:
        name = "test"

        async def run_once(self) -> None:
            return None

    first_hook = _Hook()
    second_hook = _Hook()
    first_runtime_hook = _RuntimeHook()
    second_runtime_hook = _RuntimeHook()
    first_job = _Job()
    second_job = _Job()
    features = (
        FeatureDefinition(
            name="first",
            learning_hooks=(first_hook,),
            runtime_learning_hooks=(first_runtime_hook,),
            background_loop_tasks=(first_job,),
        ),
        FeatureDefinition(
            name="second",
            learning_hooks=(second_hook,),
            runtime_learning_hooks=(second_runtime_hook,),
            background_loop_tasks=(second_job,),
        ),
    )
    assert collect_learning_hooks(features) == (first_hook, second_hook)
    assert collect_runtime_learning_hooks(features) == (first_runtime_hook, second_runtime_hook)
    assert collect_background_loop_tasks(features) == (first_job, second_job)
