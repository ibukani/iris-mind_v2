"""Tests for runtime logging setup."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from pathlib import Path

from iris.runtime.config.logging import RuntimeLoggingConfig
from iris.runtime.observability.logging import configure_runtime_logging


def test_configure_runtime_logging_text() -> None:
    """Test configuring text logging without file."""
    config = RuntimeLoggingConfig(level="DEBUG", format="text")
    # This should not raise an error
    configure_runtime_logging(config)


def test_configure_runtime_logging_json() -> None:
    """Test configuring json logging without file."""
    config = RuntimeLoggingConfig(level="INFO", format="json")
    configure_runtime_logging(config)


def test_configure_runtime_logging_with_file(tmp_path: Path) -> None:
    """Test configuring logging with a file path."""
    log_file = tmp_path / "logs" / "iris.log"
    config = RuntimeLoggingConfig(
        level="INFO",
        format="json",
        file_path=str(log_file),
    )
    configure_runtime_logging(config)

    # Verify parent directory was created
    assert log_file.parent.exists()
    assert log_file.parent.is_dir()

    # Log something to verify file creation
    logger.info("Test message")
    assert log_file.exists()
