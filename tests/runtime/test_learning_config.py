"""Runtime learning configuration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.runtime.config import default_runtime_config, load_runtime_config
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
        relationship_update_candidates_enabled = true
        implicit_candidate_min_confidence = 0.5
        implicit_candidate_max_text_length = 512
        """,
        encoding="utf-8",
    )

    config = load_runtime_config(config_path, env={})

    assert config.learning.implicit_candidates_enabled is False
    assert config.learning.relationship_update_candidates_enabled is True
    assert config.learning.implicit_candidate_min_confidence == approx(0.5)
    assert config.learning.implicit_candidate_max_text_length == 512


def test_builtin_memory_extraction_policy_is_deterministic_by_default() -> None:
    """Built-in implicit memory extraction は初期値では LLM 資源を要求しない。"""
    kinds = default_runtime_config().learning.background_job_policy.kinds

    assert kinds.memory_extraction.uses_llm is False
    assert kinds.reflection.uses_llm is True
