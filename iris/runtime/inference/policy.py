"""ローカル推論資源 lease policy。"""

from __future__ import annotations

from dataclasses import dataclass

from iris.runtime.inference.models import InferenceLeaseDecision, InferenceWorkPriority


@dataclass(frozen=True)
class LocalInferenceResourcePolicy:
    """軽量 scheduler が参照する推論資源 policy。"""

    enabled: bool = False
    large_llm_concurrency_limit: int = 1
    small_classifier_concurrency_limit: int = 4
    embedding_concurrency_limit: int = 2
    reranker_concurrency_limit: int = 2
    preempt_background_for_user_facing: bool = True
    background_when_busy: InferenceLeaseDecision = InferenceLeaseDecision.DEFER
    proactive_when_busy: InferenceLeaseDecision = InferenceLeaseDecision.NO_SEND
    low_priority_when_warming: InferenceLeaseDecision = InferenceLeaseDecision.DEFER
    background_when_unavailable: InferenceLeaseDecision = InferenceLeaseDecision.CANCEL
    proactive_when_unavailable: InferenceLeaseDecision = InferenceLeaseDecision.NO_SEND
    user_facing_when_unavailable: InferenceLeaseDecision = InferenceLeaseDecision.DENIED

    def busy_decision_for(self, priority: InferenceWorkPriority) -> InferenceLeaseDecision:
        """Busy 時の低優先度 lease decision を返す。

        Returns:
            InferenceLeaseDecision: priority に対応する非blocking decision。
        """
        if priority is InferenceWorkPriority.PROACTIVE:
            return self.proactive_when_busy
        return self.background_when_busy

    def unavailable_decision_for(self, priority: InferenceWorkPriority) -> InferenceLeaseDecision:
        """Unavailable 時の lease decision を返す。

        Returns:
            InferenceLeaseDecision: priority に対応する非blocking decision。
        """
        if priority is InferenceWorkPriority.PROACTIVE:
            return self.proactive_when_unavailable
        if priority in {
            InferenceWorkPriority.USER_FACING_RESPONSE,
            InferenceWorkPriority.SAFETY_CRITICAL,
        }:
            return self.user_facing_when_unavailable
        return self.background_when_unavailable
