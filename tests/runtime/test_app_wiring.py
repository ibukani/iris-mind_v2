"""Tests for runtime app wiring helper functions."""

from __future__ import annotations

from iris.adapters.llm.openai import OpenAIConfig
from iris.runtime.app import IrisApp
from iris.runtime.wiring.app import wire_ollama_app, wire_openai_app


def test_wire_openai_app_with_config() -> None:
    """wire_openai_app with explicit config skips env lookup."""
    config = OpenAIConfig(model="gpt-test", api_key="test-key")
    app = wire_openai_app(config=config)
    assert isinstance(app, IrisApp)


def test_wire_ollama_app_without_config_uses_defaults() -> None:
    """wire_ollama_app with config=None uses built-in defaults."""
    app = wire_ollama_app(config=None, model="qwen3:8b")
    assert isinstance(app, IrisApp)
