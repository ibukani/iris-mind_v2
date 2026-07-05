"""Persona load diagnostics の observability helper。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.runtime.observability.context import trace_counter_extra
from iris.runtime.observability.logger import LoguruRuntimeLogger

if TYPE_CHECKING:
    from iris.runtime.observability.ports import RuntimeLogger
    from iris.runtime.persona.loader import PersonaLoadDiagnostics


def record_persona_load_diagnostics(
    diagnostics: PersonaLoadDiagnostics,
    *,
    runtime_logger: RuntimeLogger | None = None,
) -> None:
    """Persona load の安全な診断情報だけを記録する。

    `persona.toml` 本文や path はログに含めず、fallback 利用有無、failure reason、
    profile version のみを残す。
    """
    logger = runtime_logger or LoguruRuntimeLogger()
    fields = trace_counter_extra()
    fields.update(
        {
            "fallback_used": diagnostics.fallback_used,
            "failure_reason": (
                None if diagnostics.failure_reason is None else diagnostics.failure_reason.value
            ),
            "profile_version": diagnostics.profile_version,
        }
    )
    logger.info("runtime.persona.load", **fields)
