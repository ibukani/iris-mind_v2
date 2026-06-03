from __future__ import annotations

from iris.adapters.memory.ports import MemoryStore
from iris.cognitive.affect.appraisal import AppraisalStep
from iris.cognitive.affect.relationship import InMemoryRelationshipState, RelationshipStep
from iris.cognitive.cycle.models import PipelineStepResult
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.cycle.service import CognitiveCycle
from iris.cognitive.memory.retrieval import MemoryRetrievalStep
from iris.cognitive.perception.basic import SimplePerceptionStep
from iris.cognitive.policy.inhibition import PolicyInhibitionStep
from iris.features.definition import FeatureDefinition
from iris.features.proactive_talk import define_proactive_talk_feature
from iris.runtime.wiring.cognitive import wire_cognitive_cycle


def wire_proactive_talk_feature(salience_threshold: float = 0.5) -> FeatureDefinition:
    return define_proactive_talk_feature(salience_threshold=salience_threshold)


def wire_proactive_talk_cognitive_cycle(
    memory_store: MemoryStore | None = None,
    relationship_state: InMemoryRelationshipState | None = None,
    salience_threshold: float = 0.5,
) -> CognitiveCycle:
    feature = wire_proactive_talk_feature(salience_threshold=salience_threshold)
    steps: list[PipelineStep[PipelineStepResult]] = [SimplePerceptionStep()]
    if memory_store is not None:
        steps.append(MemoryRetrievalStep(memory_store))
    steps.extend(
        (
            AppraisalStep(),
            RelationshipStep(relationship_state or InMemoryRelationshipState()),
            PolicyInhibitionStep(),
            *feature.pipeline_steps,
        )
    )
    return wire_cognitive_cycle(steps=tuple(steps))
