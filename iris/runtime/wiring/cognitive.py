"""認知モジュールの依存関係を組み立てる、コンストラクタ注入のみの構成。

本モジュールは PipelineStep インスタンスを CognitiveCycle に組み込む。レジストリも
認知ポリシーロジックも含まない。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.cognitive.action.response import ResponseGenerationStep
from iris.cognitive.affect.appraisal import AppraisalStep
from iris.cognitive.affect.relationship import InMemoryRelationshipState, RelationshipStep
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.service import CognitiveCycle
from iris.cognitive.memory.retrieval import MemoryRetrievalStep, MemoryRetriever
from iris.cognitive.memory.write import MemoryWriteStep
from iris.cognitive.perception.basic import SimplePerceptionStep
from iris.cognitive.policy.inhibition import PolicyInhibitionStep
from iris.contracts.actions import ActionPlan
from iris.contracts.memory import MemoryStore, MutableMemoryStore, VectorMemoryIndex
from iris.runtime.wiring.llm import wire_response_generator

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.adapters.llm.ports import LLMClient
    from iris.cognitive.cycle.models import PipelineStepResult
    from iris.cognitive.cycle.pipeline import PipelineStep


def wire_cognitive_cycle(
    steps: Sequence[PipelineStep[PipelineStepResult]],
    fallback_plan: ActionPlan | None = None,
) -> CognitiveCycle:
    """明示的なパイプラインステップから CognitiveCycle を組み立てる。

    Args:
        steps: 1 ターンごとに実行するパイプラインステップの順序付き列。
        fallback_plan: サイクルが結果を生成しない場合に返すプラン。

    Returns:
        構成済みの CognitiveCycle。
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


def wire_text_response_cognitive_cycle(
    llm_client: LLMClient | None = None,
    *,
    model: str = "fake-llm",
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> CognitiveCycle:
    """デフォルトの 1 ターンテキスト応答向け認知サイクルを組み立てる。

    Args:
        llm_client: 任意の LLM クライアントオーバーライド。
        model: 応答生成に渡すモデル名。
        temperature: 応答生成に渡すサンプリング温度。
        max_tokens: 応答生成に渡す任意の出力トークン上限。

    Returns:
        知覚と応答生成ステップを含む CognitiveCycle。
    """
    return wire_cognitive_cycle(
        steps=(
            SimplePerceptionStep(),
            ResponseGenerationStep(
                wire_response_generator(
                    llm_client,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            ),
        ),
    )


def wire_memory_aware_text_response_cognitive_cycle(
    memory_store: MemoryStore,
    llm_client: LLMClient | None = None,
    *,
    model: str = "fake-llm",
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> CognitiveCycle:
    """メモリ検索付きのテキスト応答向け認知サイクルを組み立てる。

    Args:
        memory_store: 取得に利用するメモリストア。
        llm_client: 任意の LLM クライアントオーバーライド。
        model: 応答生成に渡すモデル名。
        temperature: 応答生成に渡すサンプリング温度。
        max_tokens: 応答生成に渡す任意の出力トークン上限。

    Returns:
        知覚・メモリ検索・応答生成を含む CognitiveCycle。
    """
    return wire_cognitive_cycle(
        steps=(
            SimplePerceptionStep(),
            MemoryRetrievalStep(memory_store),
            ResponseGenerationStep(
                wire_response_generator(
                    llm_client,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            ),
        ),
    )


def wire_affect_memory_aware_text_response_cognitive_cycle(
    memory_store: MemoryStore | None = None,
    llm_client: LLMClient | None = None,
    relationship_state: InMemoryRelationshipState | None = None,
    *,
    memory_retriever: MemoryRetriever | None = None,
    vector_index: VectorMemoryIndex | None = None,
    response_generator: ResponseGenerationStep | None = None,
) -> CognitiveCycle:
    """感情と任意のメモリを含むテキスト応答向け認知サイクルを組み立てる。

    Args:
        memory_store: 任意の取得用メモリストア。
        llm_client: 任意の LLM クライアントオーバーライド。
        relationship_state: 任意の共有関係状態。
        memory_retriever: 任意のメモリ検索レトリーバー。指定時は memory_store より優先。
        vector_index: ベクトル検索インデックス。指定時は MemoryWriteStep で upsert する。
        response_generator: 任意の応答生成ステップ。省略時はデフォルト生成器を使用。

    Returns:
        知覚・任意のメモリ・アプレイザル・関係・応答生成を含む CognitiveCycle。
    """
    steps: list[PipelineStep[PipelineStepResult]] = [SimplePerceptionStep()]
    if memory_retriever is not None:
        steps.append(MemoryRetrievalStep(memory_retriever))
    elif memory_store is not None:
        steps.append(MemoryRetrievalStep(memory_store))
    if memory_store is not None and isinstance(memory_store, MutableMemoryStore):
        steps.append(MemoryWriteStep(store=memory_store, vector_index=vector_index))
    if response_generator is None:
        response_generator = ResponseGenerationStep(wire_response_generator(llm_client))
    steps.extend(
        (
            AppraisalStep(),
            RelationshipStep(relationship_state or InMemoryRelationshipState()),
            response_generator,
        )
    )
    return wire_cognitive_cycle(steps=tuple(steps))


def wire_policy_affect_memory_aware_text_response_cognitive_cycle(
    memory_store: MemoryStore | None = None,
    llm_client: LLMClient | None = None,
    relationship_state: InMemoryRelationshipState | None = None,
    *,
    memory_retriever: MemoryRetriever | None = None,
    vector_index: VectorMemoryIndex | None = None,
    response_generator: ResponseGenerationStep | None = None,
) -> CognitiveCycle:
    """ポリシー・感情・メモリを含むテキスト応答向け認知サイクルを組み立てる。

    Args:
        memory_store: 任意の取得用メモリストア。
        llm_client: 任意の LLM クライアントオーバーライド。
        relationship_state: 任意の共有関係状態。
        memory_retriever: 任意のメモリ検索レトリーバー。指定時は memory_store より優先。
        vector_index: ベクトル検索インデックス。指定時は MemoryWriteStep で upsert する。
        response_generator: 任意の応答生成ステップ。省略時はデフォルト生成器を使用。

    Returns:
        知覚・任意のメモリ・書き込み・アプレイザル・関係・
        ポリシー抑制・応答生成を含む CognitiveCycle。
    """
    steps: list[PipelineStep[PipelineStepResult]] = [SimplePerceptionStep()]
    if memory_retriever is not None:
        steps.append(MemoryRetrievalStep(memory_retriever))
    elif memory_store is not None:
        steps.append(MemoryRetrievalStep(memory_store))
    if memory_store is not None and isinstance(memory_store, MutableMemoryStore):
        steps.append(MemoryWriteStep(store=memory_store, vector_index=vector_index))
    if response_generator is None:
        response_generator = ResponseGenerationStep(wire_response_generator(llm_client))
    steps.extend(
        (
            AppraisalStep(),
            RelationshipStep(relationship_state or InMemoryRelationshipState()),
            PolicyInhibitionStep(),
            response_generator,
        )
    )
    return wire_cognitive_cycle(steps=tuple(steps))
