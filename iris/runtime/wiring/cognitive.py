"""Constructor-injection-only composition for cognitive module dependencies.

This module wires PipelineStep instances into a CognitiveCycle. It contains no
registry and no cognitive policy logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.cognitive.action.response import ResponseGenerationStep
from iris.cognitive.affect.appraisal import AppraisalStep
from iris.cognitive.affect.relationship import InMemoryRelationshipState, RelationshipStep
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.service import CognitiveCycle
from iris.cognitive.memory.retrieval import MemoryRetrievalStep
from iris.cognitive.perception.basic import SimplePerceptionStep
from iris.cognitive.policy.inhibition import PolicyInhibitionStep
from iris.contracts.actions import ActionPlan
from iris.runtime.wiring.llm import wire_response_generator

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.adapters.llm.ports import LLMClient
    from iris.adapters.memory.ports import MemoryStore
    from iris.cognitive.cycle.models import PipelineStepResult
    from iris.cognitive.cycle.pipeline import PipelineStep


def wire_cognitive_cycle(
    steps: Sequence[PipelineStep[PipelineStepResult]],
    fallback_plan: ActionPlan | None = None,
) -> CognitiveCycle:
    """Wire a CognitiveCycle with the given pipeline steps.

    Args:
        steps: Ordered pipeline steps to execute per turn.
        fallback_plan: Plan returned when the cycle produces no result.

    Returns:
        A configured CognitiveCycle instance.
    """
    if fallback_plan is None:
        fallback_plan = ActionPlan(
            turn_intent="no_action",
            candidate_text=None,
            should_respond=False,
            priority=-1,
        )
    return CognitiveCycle(
        steps=steps,
        frame_builder=FrameBuilder(),
        fallback_plan=fallback_plan,
    )


def wire_text_response_cognitive_cycle(llm_client: LLMClient | None = None) -> CognitiveCycle:
    """Wire a minimal text-response cognitive cycle.

    Args:
        llm_client: Optional LLM client override.

    Returns:
        A CognitiveCycle with perception and response generation steps.
    """
    return wire_cognitive_cycle(
        steps=(
            SimplePerceptionStep(),
            ResponseGenerationStep(wire_response_generator(llm_client)),
        ),
    )


def wire_memory_aware_text_response_cognitive_cycle(
    memory_store: MemoryStore,
    llm_client: LLMClient | None = None,
) -> CognitiveCycle:
    """Wire a text-response cognitive cycle with memory retrieval.

    Args:
        memory_store: Memory store for retrieval.
        llm_client: Optional LLM client override.

    Returns:
        A CognitiveCycle with perception, memory, and response generation steps.
    """
    return wire_cognitive_cycle(
        steps=(
            SimplePerceptionStep(),
            MemoryRetrievalStep(memory_store),
            ResponseGenerationStep(wire_response_generator(llm_client)),
        ),
    )


def wire_affect_memory_aware_text_response_cognitive_cycle(
    memory_store: MemoryStore | None = None,
    llm_client: LLMClient | None = None,
    relationship_state: InMemoryRelationshipState | None = None,
) -> CognitiveCycle:
    """Wire a text-response cognitive cycle with affect and optional memory.

    Args:
        memory_store: Optional memory store for retrieval.
        llm_client: Optional LLM client override.
        relationship_state: Optional shared relationship state.

    Returns:
        A CognitiveCycle with perception, optional memory, appraisal,
        relationship, and response generation steps.
    """
    steps: list[PipelineStep[PipelineStepResult]] = [SimplePerceptionStep()]
    if memory_store is not None:
        steps.append(MemoryRetrievalStep(memory_store))
    steps.extend(
        (
            AppraisalStep(),
            RelationshipStep(relationship_state),
            ResponseGenerationStep(wire_response_generator(llm_client)),
        )
    )
    return wire_cognitive_cycle(steps=tuple(steps))


def wire_policy_affect_memory_aware_text_response_cognitive_cycle(
    memory_store: MemoryStore | None = None,
    llm_client: LLMClient | None = None,
    relationship_state: InMemoryRelationshipState | None = None,
) -> CognitiveCycle:
    """Wire a text-response cognitive cycle with policy, affect, and optional memory.

    Args:
        memory_store: Optional memory store for retrieval.
        llm_client: Optional LLM client override.
        relationship_state: Optional shared relationship state.

    Returns:
        A CognitiveCycle with perception, optional memory, appraisal,
        relationship, policy inhibition, and response generation steps.
    """
    steps: list[PipelineStep[PipelineStepResult]] = [SimplePerceptionStep()]
    if memory_store is not None:
        steps.append(MemoryRetrievalStep(memory_store))
    steps.extend(
        (
            AppraisalStep(),
            RelationshipStep(relationship_state or InMemoryRelationshipState()),
            PolicyInhibitionStep(),
            ResponseGenerationStep(wire_response_generator(llm_client)),
        )
    )
    return wire_cognitive_cycle(steps=tuple(steps))
