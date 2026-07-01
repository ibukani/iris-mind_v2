"""Runtime learning configuration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.runtime.config import load_runtime_config
from tests.helpers.approx import approx

if TYPE_CHECKING:
    from pathlib import Path


def test_toml_sets_implicit_learning_candidate_options(tmp_path: Path) -> None:
    """TOML can configure implicit memory candidate review settings."""
    config_path = tmp_path / "runtime.toml"
    config_path.write_text(
        """
        [learning]
        implicit_candidates_enabled = false
        implicit_candidate_min_confidence = 0.5
        implicit_candidate_max_text_length = 512
        """,
        encoding="utf-8",
    )

    config = load_runtime_config(config_path, env={})

    assert config.learning.implicit_candidates_enabled is False
    assert config.learning.implicit_candidate_min_confidence == approx(0.5)
    assert config.learning.implicit_candidate_max_text_length == 512
