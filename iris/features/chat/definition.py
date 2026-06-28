"""応答生成パイプラインステップとサポート型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, override

from iris.cognitive.cycle.models import ActionSelectionResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.workspace.frame import WorkspaceFrame, interpreted_input_text
from iris.contracts.actions import ActionPlan
from iris.contracts.observations import ActorMessageObservation

if TYPE_CHECKING:
    from iris.contracts.policy import PolicyConstraint


@dataclass(frozen=True)
class ResponsePrompt:
    """LLM用にワークスペースフレームから組み立てられたプロンプトデータ。"""

    system_instruction: str
    actor_text: str
    memory_snippets: tuple[str, ...] = ()
    affect_context: str | None = None
    relationship_context: str | None = None
    goals: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeneratedResponse:
    """LLMによって生成された応答。"""

    text: str
    model: str


class ResponseGenerator(Protocol):
    """LLM応答生成器のプロトコル。"""

    async def generate_response(self, prompt: ResponsePrompt) -> GeneratedResponse:
        """与えられたプロンプトから応答を生成する。"""
        ...


def build_response_prompt(frame: WorkspaceFrame) -> ResponsePrompt | None:
    """ワークスペースフレームからResponsePromptを組み立てる。入力テキストがない場合はNone。

    Returns:
        ResponsePrompt | None: 構築された応答プロンプト。入力テキストがない場合は None。
    """
    if not isinstance(frame.observation, ActorMessageObservation):
        return None
    text = interpreted_input_text(frame)
    if text is None:
        return None

    return ResponsePrompt(
        system_instruction=(
            "Generate a concise text response for Iris. "
            "Respond directly without showing your thinking or reasoning process."
        ),
        actor_text=text,
        memory_snippets=tuple(
            result.record.text for result in frame.memory_summary.retrieved_memories
        ),
        affect_context=frame.affect.affect_summary,
        relationship_context=frame.relationship.relationship_summary,
        goals=tuple(goal.name for goal in frame.goals),
        constraints=tuple(
            _format_policy_constraint(constraint) for constraint in frame.constraints
        ),
    )


def _format_policy_constraint(constraint: PolicyConstraint) -> str:
    return constraint.prompt_instruction or constraint.name


class ResponseGenerationStep(PipelineStep[ActionSelectionResult]):
    """LLMを介してテキスト応答を生成するパイプラインステップ。"""

    name = "response_generation"

    def __init__(self, generator: ResponseGenerator, *, priority: int = 10) -> None:
        """応答生成器とオプションの優先度で初期化する。

        Args:
            generator: 使用する応答生成器。
            priority: 生成される ActionPlan の優先度。
        """
        self._generator = generator
        self._priority = priority

    @override
    async def run(self, frame: WorkspaceFrame) -> ActionSelectionResult:
        """応答を生成し、アクション選択結果を返す。

        Returns:
            ActionSelectionResult: 生成されたアクションプラン。入力がない場合は SKIPPED。
        """
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
