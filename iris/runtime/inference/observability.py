"""推論資源 scheduler decision の観測補助。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.runtime.observability.context import trace_counter_extra

if TYPE_CHECKING:
    from iris.runtime.inference.models import InferenceLeaseResult


def inference_lease_log_fields(result: InferenceLeaseResult) -> dict[str, str | int | float | None]:
    """Prompt / payload を含まない lease decision log field を返す。

    Returns:
        logger に渡せる安全な field 群。
    """
    fields: dict[str, str | int | float | None] = {
        "decision": result.decision.value,
        "reason": result.reason,
        "resource_state": result.snapshot.state.value,
        "slot_kind": result.request.slot_kind.value,
        "priority": result.request.priority.value,
        "call_site": result.request.call_site.value,
        "model_slot": result.request.model_slot,
        "model_name": result.request.model_name,
        "active_large_slots": result.snapshot.active_large_slots,
        "active_small_classifier_slots": result.snapshot.active_small_classifier_slots,
        "active_embedding_slots": result.snapshot.active_embedding_slots,
        "active_reranker_slots": result.snapshot.active_reranker_slots,
        "busy_duration_seconds": result.snapshot.busy_duration_seconds,
        "cancelled_lease_count": len(result.cancelled_lease_ids),
    }
    fields.update(trace_counter_extra())
    return fields
