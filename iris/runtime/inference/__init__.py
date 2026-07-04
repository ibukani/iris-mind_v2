"""ローカル推論資源 scheduler boundary。"""

from __future__ import annotations

from iris.runtime.inference.models import (
    InferenceLeaseDecision,
    InferenceLeaseRequest,
    InferenceLeaseResult,
    InferenceResourceSnapshot,
    InferenceResourceState,
    InferenceSlotKind,
    InferenceWorkPriority,
    model_call_site_priority,
)
from iris.runtime.inference.policy import LocalInferenceResourcePolicy
from iris.runtime.inference.scheduler import LocalInferenceResourceScheduler

__all__ = (
    "InferenceLeaseDecision",
    "InferenceLeaseRequest",
    "InferenceLeaseResult",
    "InferenceResourceSnapshot",
    "InferenceResourceState",
    "InferenceSlotKind",
    "InferenceWorkPriority",
    "LocalInferenceResourcePolicy",
    "LocalInferenceResourceScheduler",
    "model_call_site_priority",
)
