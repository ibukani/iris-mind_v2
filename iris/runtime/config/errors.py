"""Runtime configuration error types."""

from __future__ import annotations


class ConfigError(RuntimeError):
    """Raised when runtime configuration is invalid."""
