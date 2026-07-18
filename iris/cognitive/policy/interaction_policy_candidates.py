"""Deterministic interaction-policy candidate admission policy."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from iris.contracts.interaction_policy import (
    InteractionPolicyCandidate,
    InteractionPolicyDecisionKind,
    InteractionPolicySignal,
    InteractionPolicySourceKind,
)
from iris.core.metadata import immutable_metadata

if TYPE_CHECKING:
    from collections.abc import Iterable

    from iris.contracts.metadata import ImmutableMetadata
    from iris.core.ids import AccountId, ActorId, SpaceId


def compute_interaction_policy_candidates(
    signals: Iterable[InteractionPolicySignal],
    *,
    account_id: AccountId,
    space_id: SpaceId | None = None,
    actor_id: ActorId | None = None,
    min_implicit_evidence: int = 2,
    min_implicit_confidence: float = 0.65,
) -> tuple[InteractionPolicyCandidate, ...]:
    """Signals を scope-bound review candidate に変換する。

    明示 feedback は一件でも候補化する。implicit signal は同じ policy/value の
    signal が最低件数と confidence 閾値を満たす場合だけ候補化する。high-risk は
    candidate として記録するが suppressed のまま promotion できない。

    Returns:
        Scope と provenance を保持した候補列。

    Raises:
        ValueError: evidence または confidence の設定が不正な場合。
    """
    if min_implicit_evidence < 1:
        message = "min_implicit_evidence must be greater than zero"
        raise ValueError(message)
    if not 0.0 <= min_implicit_confidence <= 1.0:
        message = "min_implicit_confidence must be between zero and one"
        raise ValueError(message)

    grouped: dict[tuple[str, str], list[InteractionPolicySignal]] = defaultdict(list)
    for signal in signals:
        grouped[signal.policy_kind.value, signal.value.strip()].append(signal)

    candidates: list[InteractionPolicyCandidate] = []
    for key in sorted(grouped):
        group = _unique_signals(grouped[key])
        candidate = _candidate_for_group(
            group,
            account_id=account_id,
            space_id=space_id,
            actor_id=actor_id,
            min_implicit_evidence=min_implicit_evidence,
            min_implicit_confidence=min_implicit_confidence,
        )
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


def _candidate_for_group(
    signals: tuple[InteractionPolicySignal, ...],
    *,
    account_id: AccountId,
    space_id: SpaceId | None,
    actor_id: ActorId | None,
    min_implicit_evidence: int,
    min_implicit_confidence: float,
) -> InteractionPolicyCandidate | None:
    explicit = any(
        signal.source is InteractionPolicySourceKind.EXPLICIT_FEEDBACK for signal in signals
    )
    implicit = all(
        signal.source is InteractionPolicySourceKind.IMPLICIT_REPEATED_SIGNAL for signal in signals
    )
    if (
        not explicit
        and implicit
        and (
            len(signals) < min_implicit_evidence
            or min(signal.confidence for signal in signals) < min_implicit_confidence
        )
    ):
        return None
    if (
        not explicit
        and not implicit
        and max(signal.confidence for signal in signals) < min_implicit_confidence
    ):
        return None

    high_risk = any(signal.high_risk for signal in signals)
    source_kinds = tuple(sorted({signal.source for signal in signals}, key=_source_sort_key))
    source_event_ids = tuple(signal.source_event_id for signal in signals)
    first = signals[0]
    model_metadata = _merge_metadata(signals)
    decision = (
        InteractionPolicyDecisionKind.SUPPRESSED
        if high_risk
        else InteractionPolicyDecisionKind.REVIEW_REQUIRED
    )
    reason = (
        "high-risk context suppressed interaction policy candidate"
        if high_risk
        else _candidate_reason(source_kinds, len(signals))
    )
    return InteractionPolicyCandidate(
        policy_kind=first.policy_kind,
        value=first.value.strip(),
        account_id=account_id,
        space_id=space_id,
        actor_id=actor_id,
        decision_kind=decision,
        source_kinds=source_kinds,
        evidence_count=len(signals),
        source_event_ids=source_event_ids,
        confidence=max(signal.confidence for signal in signals),
        reason=reason,
        high_risk=high_risk,
        model_metadata=model_metadata,
        metadata=immutable_metadata({"generator": "deterministic_baseline"}),
    )


def _unique_signals(signals: list[InteractionPolicySignal]) -> tuple[InteractionPolicySignal, ...]:
    by_event_id = {signal.source_event_id: signal for signal in signals}
    return tuple(sorted(by_event_id.values(), key=_signal_sort_key))


def _signal_sort_key(signal: InteractionPolicySignal) -> tuple[object, str]:
    return signal.occurred_at, signal.source_event_id


def _source_sort_key(source: InteractionPolicySourceKind) -> str:
    return source.value


def _merge_metadata(signals: tuple[InteractionPolicySignal, ...]) -> ImmutableMetadata:
    values: dict[str, str] = {}
    for signal in signals:
        values.update(signal.model_metadata)
    return immutable_metadata(values)


def _candidate_reason(source_kinds: tuple[InteractionPolicySourceKind, ...], count: int) -> str:
    if InteractionPolicySourceKind.EXPLICIT_FEEDBACK in source_kinds:
        return "explicit response-style feedback has priority"
    if InteractionPolicySourceKind.IMPLICIT_REPEATED_SIGNAL in source_kinds:
        return f"repeated implicit response-style signal met evidence threshold ({count})"
    return "review-required policy candidate from bounded classifier metadata"
