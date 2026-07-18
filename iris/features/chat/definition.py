"""応答生成パイプラインステップとサポート型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, override

from iris.cognitive.cycle.models import ActionSelectionResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.workspace.frame import WorkspaceFrame, interpreted_input_text
from iris.contracts.actions import ActionPlan
from iris.contracts.model_policy import CascadeDecision
from iris.contracts.observations import ActorMessageObservation
from iris.contracts.prompting import PromptSectionKind
from iris.contracts.retrieval import (
    RetrievalQuery,
    RetrievalSourceKind,
    RetrievalSourceScope,
    RetrievedContextItem,
)
from iris.features.definition import FeatureDefinition

if TYPE_CHECKING:
    from iris.contracts.conversation import ConversationRecord
    from iris.contracts.model_policy import CascadeResult
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
    conversation_history: tuple[ConversationRecord, ...] = ()
    conversation_summary: str | None = None
    retrieved_context: tuple[RetrievedContextItem, ...] = ()
    retrieval_query: RetrievalQuery | None = None


@dataclass(frozen=True)
class GeneratedResponse:
    """LLMによって生成された応答。"""

    text: str
    model: str
    cascade_result: CascadeResult | None = None


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

    scope = RetrievalSourceScope(
        actor_id=(frame.actor_context.actor.actor_id if frame.actor_context.actor else None),
        account_id=frame.actor_context.account_id,
        space_id=frame.space_context.space_id,
        session_id=frame.observation.session_id,
    )
    retrieved_context = tuple(
        RetrievedContextItem(
            source_id=str(result.record.id),
            source_kind=RetrievalSourceKind.DURABLE_MEMORY,
            prompt_section_kind=PromptSectionKind.USER_MEMORY,
            text=result.record.text,
            score=result.score,
            reason="cognitive memory retrieval",
            scope=scope,
            metadata=result.record.metadata,
        )
        for result in frame.memory_summary.retrieved_memories
    )
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
        conversation_history=frame.conversation_history,
        conversation_summary=frame.conversation_summary,
        retrieved_context=retrieved_context,
        retrieval_query=(
            RetrievalQuery(text=text, scope=scope)
            if any(
                value is not None for value in (scope.actor_id, scope.account_id, scope.space_id)
            )
            else None
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
        blocking_constraint = _first_blocking_constraint(frame)
        if blocking_constraint is not None:
            return _skipped_result(
                self.name,
                f"policy blocks response: {blocking_constraint.name}",
            )

        prompt = build_response_prompt(frame)
        if prompt is None:
            return _skipped_result(self.name, "no interpreted input text")

        generated = await self._generator.generate_response(prompt)
        return _generated_response_result(self.name, generated, self._priority)


def _skipped_result(step_name: str, reason: str) -> ActionSelectionResult:
    return ActionSelectionResult(
        step_name=step_name,
        status=StepStatus.SKIPPED,
        reason=reason,
    )


def _generated_response_result(
    step_name: str,
    generated: GeneratedResponse,
    priority: int,
) -> ActionSelectionResult:
    if _cascade_blocks_response(generated):
        cascade_result = generated.cascade_result
        if cascade_result is None:
            reason = "model call blocked"
        else:
            reason = f"model call {cascade_result.decision.value}: {cascade_result.reason}"
        return _skipped_result(step_name, reason)
    if not generated.text.strip():
        return _skipped_result(step_name, "empty generated response")

    plan = ActionPlan(
        turn_intent="respond",
        candidate_text=generated.text,
        should_respond=True,
        priority=priority,
    )
    return ActionSelectionResult(
        step_name=step_name,
        status=StepStatus.OK,
        action_plans=(plan,),
    )


def _first_blocking_constraint(frame: WorkspaceFrame) -> PolicyConstraint | None:
    for constraint in frame.constraints:
        if constraint.blocks_response:
            return constraint
    return None


def _cascade_blocks_response(generated: GeneratedResponse) -> bool:
    cascade_result = generated.cascade_result
    if cascade_result is None or cascade_result.decision is CascadeDecision.ACCEPT:
        return False
    if cascade_result.decision is CascadeDecision.FALLBACK:
        return not generated.text.strip()
    return True


def define_chat_feature(generator: ResponseGenerator, *, priority: int = 10) -> FeatureDefinition:
    """LLMテキスト応答機能の定義を組み立てる。

    Args:
        generator: 使用する応答生成器。
        priority: アクションプランの優先度。

    Returns:
        Chat feature vertical sliceの定義。
    """
    return FeatureDefinition(
        name="chat",
        cognitive_steps=(ResponseGenerationStep(generator=generator, priority=priority),),
    )
