"""Persona observability tests."""

from __future__ import annotations

from iris.runtime.persona.loader import PersonaLoadDiagnostics, PersonaLoadFailureReason
from iris.runtime.persona.observability import record_persona_load_diagnostics


class RecordingLogger:
    """RuntimeLogger テストダブル。"""

    def __init__(self) -> None:
        """記録用バッファを初期化する。"""
        self.events: list[tuple[str, dict[str, str | float | bool | None]]] = []

    def debug(self, event: str, **fields: str | float | bool | None) -> None:
        self.events.append((event, dict(fields)))

    def info(self, event: str, **fields: str | float | bool | None) -> None:
        self.events.append((event, dict(fields)))

    def warning(self, event: str, **fields: str | float | bool | None) -> None:
        self.events.append((event, dict(fields)))

    def error(self, event: str, **fields: str | float | bool | None) -> None:
        self.events.append((event, dict(fields)))


def test_persona_load_observability_excludes_profile_text_and_path() -> None:
    """Persona loader diagnostics は本文や path を出さず安全な metadata だけを記録する。"""
    logger = RecordingLogger()

    record_persona_load_diagnostics(
        PersonaLoadDiagnostics(
            fallback_used=True,
            failure_reason=PersonaLoadFailureReason.VALIDATION_ERROR,
            profile_version="fallback-1",
        ),
        runtime_logger=logger,
    )

    assert len(logger.events) == 1
    event, fields = logger.events[0]
    assert event == "runtime.persona.load"
    assert fields["fallback_used"] is True
    assert fields["failure_reason"] == "validation_error"
    assert fields["profile_version"] == "fallback-1"
    forbidden_keys = {"path", "persona", "profile_text", "prompt", "text"}
    assert all(forbidden_keys.isdisjoint(fields) for _, fields in logger.events)
