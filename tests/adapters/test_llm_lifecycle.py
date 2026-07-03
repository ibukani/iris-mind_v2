"""Provider-neutral LLM lifecycle contract tests."""

from __future__ import annotations

from iris.adapters.llm.lifecycle import (
    ModelLoadState,
    cold_start_latency_ms,
    generation_latency_ms,
    generation_model_load_state,
)
from tests.helpers.approx import approx


def test_generation_state_marks_unloaded_success_as_cold_start() -> None:
    """A generation that starts from an unloaded model is a cold start."""
    state = generation_model_load_state(
        before=ModelLoadState.UNLOADED,
        load_latency_ms=None,
    )

    assert state is ModelLoadState.COLD_START


def test_generation_state_preserves_warm_state() -> None:
    """A generation that starts from a loaded model remains warm."""
    state = generation_model_load_state(
        before=ModelLoadState.WARM,
        load_latency_ms=0.0,
    )

    assert state is ModelLoadState.WARM


def test_generation_state_uses_provider_load_latency_when_state_unknown() -> None:
    """Provider load duration can identify cold start without a pre-probe."""
    state = generation_model_load_state(
        before=ModelLoadState.UNKNOWN,
        load_latency_ms=12.5,
    )

    assert state is ModelLoadState.COLD_START


def test_cold_start_latency_uses_provider_split_when_available() -> None:
    """Cold start latency prefers provider load duration."""
    latency = cold_start_latency_ms(
        load_state=ModelLoadState.COLD_START,
        load_latency_ms=15.0,
        fallback_latency_ms=200.0,
    )

    assert latency == approx(15.0)


def test_cold_start_latency_falls_back_to_wall_clock() -> None:
    """Cold start latency falls back when provider split timings are absent."""
    latency = cold_start_latency_ms(
        load_state=ModelLoadState.COLD_START,
        load_latency_ms=None,
        fallback_latency_ms=200.0,
    )

    assert latency == approx(200.0)


def test_generation_latency_prefers_provider_split() -> None:
    """Generation latency uses provider eval duration when available."""
    latency = generation_latency_ms(
        provider_generation_latency_ms=30.0,
        fallback_latency_ms=200.0,
    )

    assert latency == approx(30.0)
