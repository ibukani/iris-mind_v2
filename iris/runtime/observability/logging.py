"""Runtime observability and logging setup."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from iris.runtime.config.logging import RuntimeLoggingConfig


def configure_runtime_logging(config: RuntimeLoggingConfig) -> None:
    """Configure Loguru as the runtime logging backend.

    Args:
        config: Runtime logging configuration.
    """
    logger.remove()

    serialize = config.format == "json"

    # Add stderr sink
    logger.add(
        sys.stderr,
        level=config.level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
        if not serialize
        else "{message}",
        serialize=serialize,
    )

    # Add optional file sink
    if config.file_path is not None:
        file_path = Path(config.file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            file_path,
            level=config.level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
            if not serialize
            else "{message}",
            serialize=serialize,
            rotation=config.rotation,
            retention=config.retention,
        )
