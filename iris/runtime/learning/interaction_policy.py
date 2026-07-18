"""Default-off interaction-policy candidate queue and deterministic worker."""

from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from threading import RLock
from typing import TYPE_CHECKING

from iris.cognitive.policy.interaction_policy_candidates import (
    compute_interaction_policy_candidates,
)
from iris.contracts.appraisal import AppraisalSafetyHintKind
from iris.contracts.interaction_policy import (
    InteractionPolicyKind,
    InteractionPolicySignal,
    InteractionPolicySourceKind,
)
from iris.contracts.observations import UserFeedbackKind
from iris.core.metadata import immutable_metadata
from iris.runtime.learning.jobs import (
    BackgroundJobId,
    BackgroundJobKind,
    BackgroundJobRecord,
    BackgroundJobResourceProfile,
    InteractionPolicyJobPayload,
)
from iris.runtime.observation_router import actor_message_observation, user_feedback_observation
from iris.runtime.state.interaction_policy_candidates import (
    InteractionPolicyCandidateReviewId,
    InteractionPolicyCandidateReviewRecord,
    InteractionPolicyCandidateReviewStore,
)

if TYPE_CHECKING:
    from iris.contracts.learning import RuntimeLearningEvent
    from iris.runtime.learning.policy import BackgroundJobQueuePolicy
    from iris.runtime.learning.queue import BackgroundJobQueue


class InteractionPolicyCandidateWorker:
    """Signals を review-required policy candidate store へ変換する worker。"""

    kind = BackgroundJobKind.INTERACTION_POLICY_CANDIDATE

    def __init__(
        self,
        store: InteractionPolicyCandidateReviewStore,
        *,
        min_implicit_evidence: int = 2,
        min_implicit_confidence: float = 0.65,
    ) -> None:
        """Review store と deterministic admission threshold を注入する。"""
        self._store = store
        self._min_implicit_evidence = min_implicit_evidence
        self._min_implicit_confidence = min_implicit_confidence

    def run(self, job: BackgroundJobRecord) -> None:
        """Deterministic baseline を実行し、candidate を冪等保存する。

        Raises:
            TypeError: job payload が interaction policy 用でない場合。
        """
        payload = job.payload
        if not isinstance(payload, InteractionPolicyJobPayload):
            message = "interaction policy candidate requires InteractionPolicyJobPayload"
            raise TypeError(message)
        candidates = compute_interaction_policy_candidates(
            payload.signals,
            account_id=payload.account_id,
            space_id=payload.space_id,
            actor_id=payload.actor_id,
            min_implicit_evidence=self._min_implicit_evidence,
            min_implicit_confidence=self._min_implicit_confidence,
        )
        for candidate in candidates:
            key = f"{job.idempotency_key}|{candidate.policy_kind.value}|{candidate.value}"
            digest = sha256(key.encode()).hexdigest()
            self._store.add_nowait(
                InteractionPolicyCandidateReviewRecord(
                    candidate_id=InteractionPolicyCandidateReviewId(
                        f"interaction-policy-{digest[:24]}"
                    ),
                    candidate=candidate,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    idempotency_key=f"interaction-policy:{key}",
                    actor_id=payload.actor_id,
                    account_id=payload.account_id,
                    space_id=payload.space_id,
                    metadata=immutable_metadata(
                        {
                            "background_job_id": str(job.job_id),
                            "generator": "deterministic_baseline",
                            "review_required": "true",
                        }
                    ),
                )
            )


class InteractionPolicyCandidateEnqueueHook:
    """明示 feedback / bounded repeated signal を background queue へ送る hook。"""

    def __init__(
        self,
        queue: BackgroundJobQueue,
        *,
        max_attempts: int = 3,
        queue_policy: BackgroundJobQueuePolicy | None = None,
        max_signal_history: int = 8,
    ) -> None:
        """Queue、retry 上限、scope history を注入する。"""
        self._queue = queue
        self._max_attempts = max_attempts
        self._queue_policy = queue_policy
        self._max_signal_history = max_signal_history
        self._history: dict[
            tuple[str, str, str, str],
            tuple[InteractionPolicySignal, ...],
        ] = defaultdict(tuple)
        self._lock = RLock()

    async def after_runtime_event(self, event: RuntimeLearningEvent) -> None:
        """候補化可能な signal だけを account / space scope 付きで enqueue する。"""
        account_id = event.observation.context.account_id
        if account_id is None:
            return
        signal = _signal_from_event(event)
        if signal is None:
            return
        space_id = event.observation.context.space_id
        key = (str(account_id), str(space_id or ""), signal.policy_kind.value, signal.value)
        with self._lock:
            history = (*self._history[key], signal)[-self._max_signal_history :]
            self._history[key] = history
        payload = InteractionPolicyJobPayload(
            signals=history,
            account_id=account_id,
            space_id=space_id,
            actor_id=event.observation.context.actor_id,
        )
        job = _new_job(event, payload, self._max_attempts)
        if self._queue_policy is None:
            await self._queue.enqueue(job)
        else:
            await self._queue.enqueue_with_policy(
                job,
                now=event.occurred_at,
                policy=self._queue_policy,
            )


def _signal_from_event(event: RuntimeLearningEvent) -> InteractionPolicySignal | None:
    observation = event.observation
    feedback = user_feedback_observation(observation)
    if feedback is not None:
        if feedback.feedback_kind is not UserFeedbackKind.STYLE_PREFERENCE:
            return None
        text = feedback.text
        source = InteractionPolicySourceKind.EXPLICIT_FEEDBACK
        confidence = 0.9
    else:
        actor_message = actor_message_observation(observation)
        if actor_message is None:
            return None
        text = actor_message.text
        source = InteractionPolicySourceKind.EXPLICIT_FEEDBACK
        confidence = 0.85
    policy = _policy_from_text(text)
    if policy is None:
        return None
    high_risk = any(
        signal.safety_hint is AppraisalSafetyHintKind.DEPENDENCY_RISK
        for signal in event.appraisal_signals
    )
    return InteractionPolicySignal(
        policy_kind=policy[0],
        value=policy[1],
        source=source,
        source_event_id=str(event.source_observation_id),
        confidence=confidence,
        reason="explicit response-style preference signal",
        occurred_at=event.occurred_at,
        high_risk=high_risk,
        model_metadata=immutable_metadata({"classifier": "deterministic_baseline"}),
    )


def _policy_from_text(text: str) -> tuple[InteractionPolicyKind, str] | None:
    lowered = text.casefold()
    candidates = (
        (
            InteractionPolicyKind.VERBOSITY,
            "concise",
            ("短く", "短め", "簡潔", "concise", "brief"),
        ),
        (
            InteractionPolicyKind.VERBOSITY,
            "detailed",
            ("詳しく", "詳細", "detailed", "thorough"),
        ),
        (InteractionPolicyKind.INITIATIVE, "high", ("積極的に", "initiative", "proactive")),
        (InteractionPolicyKind.INITIATIVE, "low", ("控えめ", "受け身", "low initiative")),
        (InteractionPolicyKind.TONE, "friendly", ("親しみ", "friendly", "casual")),
        (InteractionPolicyKind.TONE, "formal", ("フォーマル", "formal")),
    )
    for policy_kind, value, markers in candidates:
        if any(marker in lowered for marker in markers):
            return policy_kind, value
    return None


def _new_job(
    event: RuntimeLearningEvent,
    payload: InteractionPolicyJobPayload,
    max_attempts: int,
) -> BackgroundJobRecord:
    key = sha256(
        "|".join(
            (
                str(event.source_observation_id),
                event.kind.value,
                event.route,
                payload.model_dump_json(),
            )
        ).encode()
    ).hexdigest()
    return BackgroundJobRecord(
        job_id=BackgroundJobId(f"interaction-policy-{key[:24]}"),
        kind=BackgroundJobKind.INTERACTION_POLICY_CANDIDATE,
        payload=payload,
        max_attempts=max_attempts,
        not_before=event.occurred_at,
        resource_profile=BackgroundJobResourceProfile(uses_llm=False),
        idempotency_key=f"interaction-policy:{key}",
        created_at=event.occurred_at,
        updated_at=event.occurred_at,
    )
