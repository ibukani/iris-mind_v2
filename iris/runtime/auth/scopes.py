"""Runtime RPC 認可 scope 定義。"""

from __future__ import annotations

from enum import StrEnum


class AuthScope(StrEnum):
    """gRPC runtime RPC に対する認可 scope。"""

    RUNTIME_INFO_READ = "runtime.info.read"
    OBSERVATION_SUBMIT = "observation.submit"
    OBSERVATION_SUBMIT_TRUSTED = "observation.submit.trusted"
    DELIVERY_POLL = "delivery.poll"
    DELIVERY_REPORT = "delivery.report"
    TRANSCRIPT_READ = "transcript.read"
    TRANSCRIPT_CLEANUP = "transcript.cleanup"
    ADMIN_RUNTIME = "admin.runtime"
