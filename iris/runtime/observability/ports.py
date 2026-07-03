"""Runtime observability ports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

RuntimeLogValue = str | int | float | bool | None
RuntimeLogFields = dict[str, RuntimeLogValue]


class RuntimeLatencyStage(StrEnum):
    """Runtime response path の段階別 latency 名。"""

    HANDLE_OBSERVATION = "handle_observation"
    OBSERVATION_INTEGRATION = "observation_integration"
    WORKSPACE_CONTEXT_ASSEMBLY = "workspace_context_assembly"
    CONVERSATION_CONTEXT_LOAD = "conversation_context_load"
    COGNITIVE_PROCESSING = "cognitive_processing"
    LLM_GENERATE = "llm_generate"
    CONVERSATION_RECORD = "conversation_record"
    TRANSCRIPT_APPEND = "transcript_append"
    RUNTIME_LEARNING_HOOK = "runtime_learning_hook"
    BACKGROUND_ENQUEUE = "background_enqueue"
    CLASSIFIER_CALL = "classifier_call"
    EMBEDDING_CALL = "embedding_call"
    RERANKER_CALL = "reranker_call"


class RuntimeModelCallKind(StrEnum):
    """Runtime trace 内で数えるモデル・分類器系 call 種別。"""

    LLM_GENERATE = "llm_generate"
    CLASSIFIER = "classifier"
    EMBEDDING = "embedding"
    RERANKER = "reranker"


@dataclass(frozen=True)
class RuntimeLatencyBudget:
    """Runtime response path の slow warning 判定 budget。"""

    enabled: bool = True
    slow_warning_enabled: bool = True
    handle_observation_ms: float = 3000.0
    observation_integration_ms: float = 50.0
    workspace_context_assembly_ms: float = 100.0
    conversation_context_load_ms: float = 100.0
    cognitive_processing_ms: float = 2500.0
    llm_generate_ms: float = 2200.0
    conversation_record_ms: float = 100.0
    transcript_append_ms: float = 100.0
    runtime_learning_hook_ms: float = 200.0
    background_enqueue_ms: float = 100.0
    classifier_call_ms: float = 50.0
    embedding_call_ms: float = 150.0
    reranker_call_ms: float = 100.0

    def budget_ms_for(self, stage: RuntimeLatencyStage) -> float:
        """Stage に対応する budget milliseconds を返す。

        Args:
            stage: latency を判定する stage。

        Returns:
            対応する budget milliseconds。
        """
        budgets: dict[RuntimeLatencyStage, float] = {
            RuntimeLatencyStage.HANDLE_OBSERVATION: self.handle_observation_ms,
            RuntimeLatencyStage.OBSERVATION_INTEGRATION: self.observation_integration_ms,
            RuntimeLatencyStage.WORKSPACE_CONTEXT_ASSEMBLY: self.workspace_context_assembly_ms,
            RuntimeLatencyStage.CONVERSATION_CONTEXT_LOAD: self.conversation_context_load_ms,
            RuntimeLatencyStage.COGNITIVE_PROCESSING: self.cognitive_processing_ms,
            RuntimeLatencyStage.LLM_GENERATE: self.llm_generate_ms,
            RuntimeLatencyStage.CONVERSATION_RECORD: self.conversation_record_ms,
            RuntimeLatencyStage.TRANSCRIPT_APPEND: self.transcript_append_ms,
            RuntimeLatencyStage.RUNTIME_LEARNING_HOOK: self.runtime_learning_hook_ms,
            RuntimeLatencyStage.BACKGROUND_ENQUEUE: self.background_enqueue_ms,
            RuntimeLatencyStage.CLASSIFIER_CALL: self.classifier_call_ms,
            RuntimeLatencyStage.EMBEDDING_CALL: self.embedding_call_ms,
            RuntimeLatencyStage.RERANKER_CALL: self.reranker_call_ms,
        }
        return budgets[stage]


class RuntimeObservationObserver(Protocol):
    """IrisRuntimeService の observation lifecycle を観測する port。"""

    def record(self, event: str, **fields: RuntimeLogValue) -> None:
        """Observation lifecycle event を記録する。"""


class RuntimeLogger(Protocol):
    """Runtime code が依存する構造化ログ port。"""

    def debug(self, event: str, **fields: RuntimeLogValue) -> None:
        """DEBUG level の runtime event を記録する。"""

    def info(self, event: str, **fields: RuntimeLogValue) -> None:
        """INFO level の runtime event を記録する。"""

    def warning(self, event: str, **fields: RuntimeLogValue) -> None:
        """WARNING level の runtime event を記録する。"""

    def error(self, event: str, **fields: RuntimeLogValue) -> None:
        """ERROR level の runtime event を記録する。"""
