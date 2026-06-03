from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from iris.cognitive.cycle.models import ActionSelectionResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.actions import ActionPlan
from iris.contracts.policy import PolicyConstraint


@dataclass(frozen=True)
class ResponsePrompt:
    system_instruction: str
    user_text: str
    memory_snippets: tuple[str, ...] = ()
    affect_context: str | None = None
    relationship_context: str | None = None
    goals: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeneratedResponse:
    text: str
    model: str


class ResponseGenerator(Protocol):
    async def generate_response(self, prompt: ResponsePrompt) -> GeneratedResponse: ...


def build_response_prompt(frame: WorkspaceFrame) -> ResponsePrompt | None:
    if frame.interpreted_input is None or frame.interpreted_input.text is None:
        return None

    return ResponsePrompt(
        system_instruction="Generate a concise text response for Iris.",
        user_text=frame.interpreted_input.text,
        memory_snippets=tuple(result.record.text for result in frame.memory_summary.retrieved_memories),
        affect_context=frame.affect.affect_summary,
        relationship_context=frame.relationship.relationship_summary,
        goals=tuple(goal.name for goal in frame.goals),
        constraints=tuple(_format_policy_constraint(constraint) for constraint in frame.constraints),
    )


def _format_policy_constraint(constraint: PolicyConstraint) -> str:
    return constraint.prompt_instruction or constraint.name


class ResponseGenerationStep(PipelineStep[ActionSelectionResult]):
    name = "response_generation"

    def __init__(self, generator: ResponseGenerator, *, priority: int = 10) -> None:
        self._generator = generator
        self._priority = priority

    async def run(self, frame: WorkspaceFrame) -> ActionSelectionResult:
        prompt = build_response_prompt(frame)
        if prompt is None:
            return ActionSelectionResult(
                step_name=self.name,
                status=StepStatus.SKIPPED,
                reason="no interpreted input text",
            )

        generated = await self._generator.generate_response(prompt)
        plan = ActionPlan(
            turn_intent="respond",
            candidate_text=generated.text,
            should_respond=bool(generated.text),
            priority=self._priority,
        )
        return ActionSelectionResult(
            step_name=self.name,
            status=StepStatus.OK,
            action_plans=(plan,),
        )
