"""Deterministic relationship update candidate worker。"""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING

from iris.cognitive.affect.relationship_update_policy import compute_relationship_update_policy
from iris.contracts.relationship_update import (
    RELATIONSHIP_UPDATE_POLICY_DEFAULTS,
    RelationshipUpdateCandidateId,
    RelationshipUpdateCandidateRecord,
    RelationshipUpdateCandidateStore,
    RelationshipUpdatePolicyConfig,
)
from iris.runtime.learning.jobs import (
    BackgroundJobId,
    BackgroundJobKind,
    BackgroundJobRecord,
    BackgroundJobResourceProfile,
    RelationshipUpdateJobPayload,
)

if TYPE_CHECKING:
    from iris.contracts.learning import RuntimeLearningEvent
    from iris.runtime.learning.policy import BackgroundJobQueuePolicy
    from iris.runtime.learning.queue import BackgroundJobQueue


_ERR_INVALID_RELATIONSHIP_PAYLOAD = "relationship update requires RelationshipUpdateJobPayload"


class RelationshipUpdateCandidateWorker:
    """Typed appraisal signals を bounded candidate に変換して保持する。"""

    kind = BackgroundJobKind.RELATIONSHIP_UPDATE

    def __init__(
        self,
        store: RelationshipUpdateCandidateStore,
        policy_config: RelationshipUpdatePolicyConfig = RELATIONSHIP_UPDATE_POLICY_DEFAULTS,
    ) -> None:
        """Candidate store と pure policy config を注入する。"""
        self._store = store
        self._policy_config = policy_config

    def run(self, job: BackgroundJobRecord) -> None:
        """Job を policy に通し、全 decision を candidate store に保存する。

        Raises:
            TypeError: payload 型が relationship update 用でない場合。
        """
        payload = job.payload
        if not isinstance(payload, RelationshipUpdateJobPayload):
            raise TypeError(_ERR_INVALID_RELATIONSHIP_PAYLOAD)
        result = compute_relationship_update_policy(
            payload.signals,
            interaction_scope=payload.interaction_scope,
            source_event_ids=payload.source_event_ids,
            config=self._policy_config,
        )
        for index, candidate in enumerate(result.candidates):
            idempotency_key = f"relationship-update:{job.idempotency_key}:{index}"
            digest = sha256(idempotency_key.encode()).hexdigest()
            self._store.add_nowait(
                RelationshipUpdateCandidateRecord(
                    candidate_id=RelationshipUpdateCandidateId(f"relationship-{digest[:24]}"),
                    candidate=candidate,
                    interaction_scope=result.interaction_scope,
                    actor_id=payload.actor_id,
                    account_id=payload.account_id,
                    space_id=payload.space_id,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    idempotency_key=idempotency_key,
                )
            )


class RelationshipUpdateCandidateEnqueueHook:
    """Typed appraisal result を relationship candidate queue へ分離する。"""

    def __init__(
        self,
        queue: BackgroundJobQueue,
        *,
        max_attempts: int = 3,
        queue_policy: BackgroundJobQueuePolicy | None = None,
    ) -> None:
        """Queue、retry 上限、pressure policy を注入する。"""
        self._queue = queue
        self._max_attempts = max_attempts
        self._queue_policy = queue_policy

    async def after_runtime_event(self, event: RuntimeLearningEvent) -> None:
        """Signal 付き post-result event だけを background queue に登録する。"""
        actor_id = event.observation.context.actor_id
        if not event.appraisal_signals or event.interaction_scope is None or actor_id is None:
            return
        payload = RelationshipUpdateJobPayload(
            signals=event.appraisal_signals,
            interaction_scope=event.interaction_scope,
            actor_id=actor_id,
            account_id=event.observation.context.account_id,
            space_id=event.observation.context.space_id,
            source_observation_id=event.source_observation_id,
            source_event_ids=event.source_event_ids,
        )
        job = _relationship_update_job(event, payload, self._max_attempts)
        if self._queue_policy is None:
            await self._queue.enqueue(job)
        else:
            await self._queue.enqueue_with_policy(
                job,
                now=event.occurred_at,
                policy=self._queue_policy,
            )


def _relationship_update_job(
    event: RuntimeLearningEvent,
    payload: RelationshipUpdateJobPayload,
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
        job_id=BackgroundJobId(f"relationship-update-{key[:24]}"),
        kind=BackgroundJobKind.RELATIONSHIP_UPDATE,
        payload=payload,
        max_attempts=max_attempts,
        not_before=event.occurred_at,
        resource_profile=BackgroundJobResourceProfile(uses_llm=False),
        idempotency_key=f"relationship-update:{key}",
        created_at=event.occurred_at,
        updated_at=event.occurred_at,
    )
