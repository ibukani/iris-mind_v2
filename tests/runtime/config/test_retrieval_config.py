"""Retrieval runtime config tests。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from iris.runtime.config import ConfigError, load_runtime_config
from iris.runtime.config.retrieval import RuntimeRetrievalConfig, apply_retrieval_toml

if TYPE_CHECKING:
    from pathlib import Path


def test_retrieval_can_be_enabled_from_toml(tmp_path: Path) -> None:
    """明示 TOML で bounded retrieval を有効化できる。"""
    default = RuntimeRetrievalConfig()
    assert default.enabled is False
    assert default.max_total_items == 12
    with pytest.raises(ConfigError):
        apply_retrieval_toml(default, {"max_total_items": -1})

    path = tmp_path / "runtime.toml"
    path.write_text(
        """
        [retrieval]
        enabled = true
        max_total_items = 4
        """,
        encoding="utf-8",
    )

    config = load_runtime_config(path)

    assert config.retrieval.enabled is True
    assert config.retrieval.max_total_items == 4
