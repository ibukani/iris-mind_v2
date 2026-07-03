"""Provider-neutral local model lifecycle state contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime


class ModelLoadState(StrEnum):
    """Provider-neutral state of a model around a generation request."""

    UNKNOWN = "unknown"
    UNLOADED = "unloaded"
    WARMING = "warming"
    WARM = "warm"
    COLD_START = "cold_start"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ModelLifecycleSnapshot:
    """Safe snapshot of a provider/model lifecycle state.

    The snapshot intentionally carries only safe operational metadata.
    It must not include prompts, user text, raw provider payloads, or
    provider credentials.

    Attributes:
        provider: Provider name that produced the snapshot.
        model: Provider-visible model name that was probed.
        load_state: Current provider-neutral model load state.
        checked_at: Optional timestamp for the snapshot.
        latency_ms: Optional probe latency in milliseconds.
        reason: Optional stable diagnostic reason safe for logs.
    """

    provider: str
    model: str
    load_state: ModelLoadState = ModelLoadState.UNKNOWN
    checked_at: datetime | None = None
    latency_ms: float | None = None
    reason: str | None = None


class ModelLifecycleProbe(Protocol):
    """Provider-neutral model lifecycle probe used by runtime wiring."""

    async def snapshot(self, model: str) -> ModelLifecycleSnapshot:
        """Return a safe lifecycle snapshot for ``model``.

        Args:
            model: Provider-visible model name to probe.

        Returns:
            Safe lifecycle snapshot for runtime request observability.
        """
        ...


def generation_model_load_state(
    *,
    before: ModelLoadState,
    load_latency_ms: float | None,
) -> ModelLoadState:
    """Classify the model state for a completed generation.

    Args:
        before: Lifecycle state observed immediately before generation.
        load_latency_ms: Provider-reported model load latency for the request.

    Returns:
        ``cold_start`` when the request loaded an unloaded model, ``warm`` when
        generation started from a loaded model, otherwise the best available
        provider-neutral state.
    """
    state = before
    if before is ModelLoadState.UNLOADED or _has_positive_latency(load_latency_ms):
        state = ModelLoadState.COLD_START
    if before is ModelLoadState.UNKNOWN and not _has_positive_latency(load_latency_ms):
        state = ModelLoadState.UNKNOWN
    return state


def cold_start_latency_ms(
    *,
    load_state: ModelLoadState,
    load_latency_ms: float | None,
    fallback_latency_ms: float,
) -> float | None:
    """Return the latency value that should be attributed to cold start.

    Args:
        load_state: Final model load state for the generation.
        load_latency_ms: Provider-reported model load latency in milliseconds.
        fallback_latency_ms: Request wall-clock latency if provider split
            timings are unavailable.

    Returns:
        Cold-start latency in milliseconds, or ``None`` for warm/unknown calls.
    """
    if load_state is not ModelLoadState.COLD_START:
        return None
    if load_latency_ms is not None:
        return load_latency_ms
    return fallback_latency_ms


def generation_latency_ms(
    *,
    provider_generation_latency_ms: float | None,
    fallback_latency_ms: float,
) -> float:
    """Return provider generation latency with wall-clock fallback.

    Args:
        provider_generation_latency_ms: Provider-reported generation duration.
        fallback_latency_ms: Request wall-clock latency.

    Returns:
        Generation latency in milliseconds.
    """
    if provider_generation_latency_ms is not None:
        return provider_generation_latency_ms
    return fallback_latency_ms


def _has_positive_latency(value: float | None) -> bool:
    return value is not None and value > 0.0
