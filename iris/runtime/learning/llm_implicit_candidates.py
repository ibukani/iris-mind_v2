"""LLM-backed implicit memory candidate worker。"""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING

from iris.contracts.implicit_memory_extraction import (
    ImplicitMemoryExtractionCandidate,
    ImplicitMemoryExtractionClient,
    ImplicitMemoryExtractionLimits,
    ImplicitMemoryExtractionRequest,
    ImplicitMemoryExtractionResult,
)
from iris.contracts.memory_candidates import (
    MemoryCandidate,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.contracts.model_policy import ModelCallDescriptor, ModelCallKind, ModelCallSite
from iris.core.metadata import immutable_metadata
from iris.runtime.learning.implicit_candidates import ImplicitCandidateAdmissionPolicy
from iris.runtime.learning.jobs import (
    BackgroundJobKind,
    BackgroundJobRecord,
    RuntimeLearningCandidateJobPayload,
)
from iris.runtime.model_call_budget import ModelCallBudgetGate
from iris.runtime.state.memory_candidates import (
    MemoryCandidateReviewId,
    MemoryCandidateReviewRecord,
)

if TYPE_CHECKING:
    from iris.runtime.inference.models import InferenceLeaseCancellationToken
    from iris.runtime.state.memory_candidates import MemoryCandidateReviewStore


class LLMImplicitMemoryCandidateWorker:
    """LLMで候補を抽出し、review storeだけへ保存する worker。

    実行時は BackgroundJobRunner が scheduler lease を先に取得する。worker 自身も
    cooperative cancellation を実装し、provider call 中の preemption を安全に止める。
    """

    kind = BackgroundJobKind.MEMORY_EXTRACTION

    def __init__(
        self,
        store: MemoryCandidateReviewStore,
        extractor: ImplicitMemoryExtractionClient,
        *,
        model: str,
        budget_gate: ModelCallBudgetGate | None = None,
        admission_policy: ImplicitCandidateAdmissionPolicy | None = None,
        limits: ImplicitMemoryExtractionLimits | None = None,
    ) -> None:
        """Review store、LLM port、model、budget、bounded admission を注入する。

        Raises:
            ValueError: model が空の場合。
        """
        if not model.strip():
            message = "LLM implicit extraction model must not be blank"
            raise ValueError(message)
        self._store = store
        self._extractor = extractor
        self._model = model
        self._budget_gate = budget_gate or ModelCallBudgetGate()
        self._admission_policy = admission_policy or ImplicitCandidateAdmissionPolicy(
            max_text_length=1000
        )
        self._limits = limits or ImplicitMemoryExtractionLimits()

    def run(self, job: BackgroundJobRecord) -> None:
        """Cancellation tokenなしで typed extraction port を実行する。"""
        self._run_blocking(job, cancellation_token=None)

    def run_with_cancellation(
        self,
        job: BackgroundJobRecord,
        cancellation_token: InferenceLeaseCancellationToken,
    ) -> None:
        """Scheduler lease の cancellation を観測して provider call を停止する。"""
        self._run_blocking(job, cancellation_token=cancellation_token)

    def _run_blocking(
        self,
        job: BackgroundJobRecord,
        *,
        cancellation_token: InferenceLeaseCancellationToken | None,
    ) -> None:
        payload = job.payload
        if not isinstance(payload, RuntimeLearningCandidateJobPayload):
            message = "LLM implicit extraction requires RuntimeLearningCandidateJobPayload"
            raise TypeError(message)
        if _cancelled(cancellation_token):
            _acknowledge_stopped(cancellation_token)
            return
        if not self._budget_allows_call():
            return
        extraction_request = _request_from_payload(
            payload,
            model=self._model,
            limits=self._limits,
        )
        result = self._extractor.extract(
            extraction_request,
            cancellation=cancellation_token,
        )
        if _cancelled(cancellation_token):
            _acknowledge_stopped(cancellation_token)
            return
        if result.failure is not None:
            return
        result = _with_worker_model(result, self._model)
        self._store_candidates(job, payload, result, cancellation_token)

    def _budget_allows_call(self) -> bool:
        descriptor = ModelCallDescriptor(
            call_kind=ModelCallKind.BACKGROUND_LLM,
            call_site=ModelCallSite.MEMORY_EXTRACTION,
            model_name=self._model,
            metadata=immutable_metadata({"worker": "llm_implicit_memory_extraction"}),
        )
        return self._budget_gate.check_and_record(descriptor).accepted

    def _store_candidates(
        self,
        job: BackgroundJobRecord,
        payload: RuntimeLearningCandidateJobPayload,
        result: ImplicitMemoryExtractionResult,
        cancellation_token: InferenceLeaseCancellationToken | None,
    ) -> None:
        for index, candidate in enumerate(result.candidates):
            if _cancelled(cancellation_token):
                _acknowledge_stopped(cancellation_token)
                return
            record = _review_record(
                job,
                payload,
                candidate,
                result=result,
                index=index,
                admission_policy=self._admission_policy,
            )
            if record is not None:
                self._store.add_nowait(record)


def _request_from_payload(
    payload: RuntimeLearningCandidateJobPayload,
    *,
    model: str,
    limits: ImplicitMemoryExtractionLimits,
) -> ImplicitMemoryExtractionRequest:
    return ImplicitMemoryExtractionRequest(
        input_text=payload.input_text,
        output_text=payload.output_text,
        source_observation_id=payload.source_observation_id,
        source_event_ids=(str(payload.source_observation_id),),
        actor_id=payload.actor_id,
        account_id=payload.account_id,
        space_id=payload.space_id,
        model_name=model,
        limits=limits,
    )


def _with_worker_model(
    result: ImplicitMemoryExtractionResult,
    model: str,
) -> ImplicitMemoryExtractionResult:
    metadata = {"model_name": model, **dict(result.model_metadata)}
    metadata["model_name"] = model
    return ImplicitMemoryExtractionResult(
        candidates=result.candidates,
        failure=result.failure,
        model_metadata=immutable_metadata(metadata),
    )


def _review_record(
    job: BackgroundJobRecord,
    payload: RuntimeLearningCandidateJobPayload,
    candidate: ImplicitMemoryExtractionCandidate,
    *,
    result: ImplicitMemoryExtractionResult,
    index: int,
    admission_policy: ImplicitCandidateAdmissionPolicy,
) -> MemoryCandidateReviewRecord | None:
    source_event_id_list = [str(payload.source_observation_id)]
    for event_id in candidate.source_event_ids:
        if event_id not in source_event_id_list:
            source_event_id_list.append(event_id)
    source_event_ids = tuple(source_event_id_list)
    model_metadata = {
        key if key.startswith("model_") else f"model_{key}": value
        for key, value in candidate.model_metadata.items()
    }
    model_metadata.update(
        {
            "model_name": result.model_metadata["model_name"],
            "model_call_site": ModelCallSite.MEMORY_EXTRACTION.value,
            "model_call_kind": ModelCallKind.BACKGROUND_LLM.value,
        }
    )
    memory_candidate = MemoryCandidate(
        text=candidate.text.strip(),
        kind=candidate.kind,
        salience=candidate.salience,
        confidence=candidate.confidence,
        source=MemoryCandidateSource.IMPLICIT_CONVERSATION,
        reason=candidate.reason,
        retention_policy=MemoryRetentionPolicy.REVIEW_REQUIRED,
        sensitivity=candidate.sensitivity,
        review_required=True,
        actor_id=payload.actor_id,
        space_id=payload.space_id,
        source_observation_id=payload.source_observation_id,
        metadata=immutable_metadata(
            {
                "extraction_mode": "llm",
                "source_event_ids": "|".join(source_event_ids),
                "high_risk": "true" if candidate.high_risk else "false",
                **model_metadata,
            }
        ),
    )
    if not admission_policy.accept(memory_candidate):
        return None
    key = _candidate_key(job, memory_candidate, index)
    return MemoryCandidateReviewRecord(
        candidate_id=MemoryCandidateReviewId(f"llm-candidate-{key[:24]}"),
        candidate=memory_candidate,
        created_at=job.created_at,
        updated_at=job.updated_at,
        idempotency_key=f"llm-candidate:{key}",
        actor_id=payload.actor_id,
        account_id=payload.account_id,
        space_id=payload.space_id,
        source_observation_id=payload.source_observation_id,
        metadata=immutable_metadata(
            {
                "background_job_id": str(job.job_id),
                "source": MemoryCandidateSource.IMPLICIT_CONVERSATION.value,
                "extraction_mode": "llm",
                "review_required": "true",
                "high_risk": "true" if candidate.high_risk else "false",
                "source_event_ids": "|".join(source_event_ids),
                **model_metadata,
            }
        ),
    )


def _candidate_key(job: BackgroundJobRecord, candidate: MemoryCandidate, index: int) -> str:
    material = f"{job.idempotency_key}|{index}|{candidate.text}|{candidate.kind.value}"
    return sha256(material.encode()).hexdigest()


def _cancelled(token: InferenceLeaseCancellationToken | None) -> bool:
    return token is not None and token.cancellation_requested


def _acknowledge_stopped(token: InferenceLeaseCancellationToken | None) -> None:
    if token is not None:
        token.acknowledge_stopped()
