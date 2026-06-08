"""Shared affect calculation helpers."""

from __future__ import annotations

_VAD_THRESHOLD = 0.2


def clamp_value(value: float, *, lower: float = -1.0, upper: float = 1.0) -> float:
    """Clamp a float value between lower and upper bounds.

    Args:
        value: The value to clamp.
        lower: Minimum allowed value.
        upper: Maximum allowed value.

    Returns:
        The clamped value.
    """
    return max(lower, min(upper, value))


def label_for_vad(valence: float, arousal: float, dominance: float) -> str | None:
    """Determine a mood label from VAD (valence/arousal/dominance) scores.

    Args:
        valence: Pleasure/displeasure dimension (-1 to 1).
        arousal: Energy/activation dimension (-1 to 1).
        dominance: Control/influence dimension (-1 to 1).

    Returns:
        A mood label string, or None if no threshold is crossed.
    """
    if valence >= _VAD_THRESHOLD:
        return "positive"
    if valence <= -_VAD_THRESHOLD:
        return "distressed" if arousal >= _VAD_THRESHOLD else "negative"
    if dominance <= -_VAD_THRESHOLD:
        return "uncertain"
    return "alert" if arousal >= _VAD_THRESHOLD else None


def format_vad_summary(
    label: str | None,
    valence: float,
    arousal: float,
    dominance: float,
) -> str:
    """Build a human-readable VAD summary string.

    Args:
        label: Mood label (or None for neutral).
        valence: Pleasure/displeasure dimension.
        arousal: Energy/activation dimension.
        dominance: Control/influence dimension.

    Returns:
        Formatted summary string like "positive VAD(v=0.50, a=0.30, d=0.10)".
    """
    label_part = label or "neutral"
    return f"{label_part} VAD(v={valence:.2f}, a={arousal:.2f}, d={dominance:.2f})"
