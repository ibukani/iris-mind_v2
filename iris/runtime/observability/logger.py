"""Loguru の上に置く runtime structured logging facade。"""

from __future__ import annotations

from typing import Protocol

from loguru import logger

from iris.runtime.observability.context import RuntimeLogFields, RuntimeLogValue, trace_extra

_SENSITIVE_FIELD_KEYS = frozenset(
    {
        "api_key",
        "password",
        "prompt",
        "prompt_text",
        "raw",
        "raw_response",
        "raw_response_body",
        "response_body",
        "secret",
        "system_instruction",
        "text",
        "token",
        "user_text",
        "user_message",
    },
)
_SENSITIVE_FIELD_SUFFIXES = (
    "_api_key",
    "_password",
    "_prompt",
    "_response_body",
    "_secret",
    "_text",
    "_token",
)


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


class LoguruRuntimeLogger:
    """Loguru backend を使う runtime structured logger。"""

    def debug(self, event: str, **fields: RuntimeLogValue) -> None:
        """DEBUG level の runtime event を記録する。"""
        self._log("debug", event, fields)

    def info(self, event: str, **fields: RuntimeLogValue) -> None:
        """INFO level の runtime event を記録する。"""
        self._log("info", event, fields)

    def warning(self, event: str, **fields: RuntimeLogValue) -> None:
        """WARNING level の runtime event を記録する。"""
        self._log("warning", event, fields)

    def error(self, event: str, **fields: RuntimeLogValue) -> None:
        """ERROR level の runtime event を記録する。"""
        self._log("error", event, fields)

    @staticmethod
    def _log(level: str, event: str, fields: RuntimeLogFields) -> None:
        safe_fields = _safe_fields(fields)
        bound_logger = logger.bind(**trace_extra(**safe_fields))
        if level == "debug":
            bound_logger.debug(event)
        elif level == "info":
            bound_logger.info(event)
        elif level == "warning":
            bound_logger.warning(event)
        else:
            bound_logger.error(event)


def _safe_fields(fields: RuntimeLogFields) -> RuntimeLogFields:
    safe: RuntimeLogFields = {}
    for key, value in fields.items():
        if _is_sensitive_key(key):
            continue
        safe[key] = value
    return safe


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return normalized in _SENSITIVE_FIELD_KEYS or normalized.endswith(_SENSITIVE_FIELD_SUFFIXES)
