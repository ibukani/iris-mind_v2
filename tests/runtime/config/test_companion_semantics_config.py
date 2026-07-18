"""Companion semantics runtime config tests。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from iris.runtime.config import ConfigError, load_runtime_config

if TYPE_CHECKING:
    from pathlib import Path


def test_companion_semantics_is_config_gated_by_default(tmp_path: Path) -> None:
    """Typed appraisal semantics は runtime config 上は明示有効化まで off。"""
    config = load_runtime_config(None, env={}, cwd=tmp_path)

    assert config.companion_semantics.appraisal_signals_enabled is False
    assert config.companion_semantics.dependency_risk_hint_enabled is True
    assert config.companion_semantics.persona_prompt_enabled is False
    assert config.companion_semantics.event_reaction_generation_enabled is False
    assert config.companion_semantics.proactive_talk_generation_enabled is False


def test_companion_semantics_can_be_enabled_explicitly(tmp_path: Path) -> None:
    """TOMLで明示した場合だけ typed appraisal signal 生成を有効化する。"""
    config = load_runtime_config(
        _write(
            tmp_path,
            """
            [companion_semantics]
            appraisal_signals_enabled = true
            dependency_risk_hint_enabled = true
            """,
        ),
        env={},
    )

    assert config.companion_semantics.appraisal_signals_enabled is True
    assert config.companion_semantics.dependency_risk_hint_enabled is True


def test_persona_prompt_can_be_enabled_explicitly(tmp_path: Path) -> None:
    """Persona hot path は typed config の明示指定でのみ有効になる。"""
    config = load_runtime_config(
        _write(
            tmp_path,
            """
            [companion_semantics]
            persona_prompt_enabled = true
            """,
        ),
        env={},
    )

    assert config.companion_semantics.persona_prompt_enabled is True


def test_event_reaction_generation_can_be_enabled_explicitly(tmp_path: Path) -> None:
    """Event reaction generationはtyped configで明示した場合だけ有効になる。"""
    config = load_runtime_config(
        _write(
            tmp_path,
            """
            [companion_semantics]
            event_reaction_generation_enabled = true
            """,
        ),
        env={},
    )

    assert config.companion_semantics.event_reaction_generation_enabled is True


def test_proactive_talk_generation_can_be_enabled_explicitly(tmp_path: Path) -> None:
    """IdleTick proactive generation は typed config の明示指定だけで有効になる。"""
    config = load_runtime_config(
        _write(
            tmp_path,
            """
            [companion_semantics]
            proactive_talk_generation_enabled = true
            """,
        ),
        env={},
    )

    assert config.companion_semantics.proactive_talk_generation_enabled is True


def test_unknown_companion_semantics_key_is_rejected(tmp_path: Path) -> None:
    """未知 key を黙って無視しない。"""
    path = _write(
        tmp_path,
        """
        [companion_semantics]
        unknown = true
        """,
    )

    with pytest.raises(ConfigError, match=r"companion_semantics\.unknown"):
        load_runtime_config(path, env={})


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "runtime.toml"
    path.write_text(content, encoding="utf-8")
    return path
