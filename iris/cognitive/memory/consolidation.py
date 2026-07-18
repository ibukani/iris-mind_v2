"""メモリ候補の決定論的 dedupe / conflict 判定。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING
import unicodedata

from iris.cognitive.memory.safety import (
    contains_credential_like_content,
    contains_sensitive_profile_content,
    is_unsafe_preferred_name_memory_text,
)
from iris.contracts.memory_candidates import MemoryCandidateSensitivity
from iris.contracts.memory_consolidation import (
    MemoryConsolidationCandidate,
    MemoryConsolidationDecisionKind,
    MemoryConsolidationSourceCandidate,
)
from iris.core.metadata import immutable_metadata

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime


@dataclass(frozen=True)
class MemoryConsolidationPolicy:
    """決定論的統合の保守的な閾値。"""

    stale_after_seconds: float = 90 * 24 * 60 * 60

    @staticmethod
    def accept(candidate: MemoryConsolidationSourceCandidate) -> bool:
        """Review boundary に残してよい候補か判定する。

        Returns:
            credential-like または unsafe な候補でない場合は True。
        """
        text = candidate.text.strip()
        return (
            bool(text)
            and contains_credential_like_content(text) is False
            and candidate.sensitivity is not MemoryCandidateSensitivity.SECRET_LIKE
            and contains_sensitive_profile_content(text) is False
            and is_unsafe_preferred_name_memory_text(text) is False
        )

    def __post_init__(self) -> None:
        """不正な stale 閾値を拒否する。

        Raises:
            ValueError: stale 閾値が正数でない場合。
        """
        if self.stale_after_seconds <= 0:
            message = "stale_after_seconds must be greater than zero"
            raise ValueError(message)


def consolidate_memory_candidates(
    candidates: tuple[MemoryConsolidationSourceCandidate, ...],
    *,
    now: datetime,
    policy: MemoryConsolidationPolicy | None = None,
) -> tuple[MemoryConsolidationCandidate, ...]:
    """候補を同一 scope 内で dedupe し、衝突を review candidate に変換する。

    canonical memory は参照も更新もしない。候補の入力順に依存しないよう、すべて
    source_candidate_id と時刻で整列する。

    Returns:
        review boundary へ渡す deterministic candidate 列。
    """
    resolved_policy = policy or MemoryConsolidationPolicy()
    unique_candidates = _unique_candidates(
        candidate for candidate in candidates if resolved_policy.accept(candidate)
    )
    stale_cutoff = now.timestamp() - resolved_policy.stale_after_seconds
    stale = tuple(
        candidate
        for candidate in unique_candidates
        if candidate.created_at.timestamp() < stale_cutoff
    )
    fresh = tuple(
        candidate
        for candidate in unique_candidates
        if candidate.created_at.timestamp() >= stale_cutoff
    )
    results: list[MemoryConsolidationCandidate] = []
    results.extend(_build_stale_result(candidate) for candidate in stale)
    results.extend(_build_group_result(group) for group in _group_by_scope_and_kind(fresh))
    return tuple(sorted(results, key=_result_sort_key))


def _unique_candidates(
    candidates: Iterable[MemoryConsolidationSourceCandidate],
) -> tuple[MemoryConsolidationSourceCandidate, ...]:
    by_id = {candidate.source_candidate_id: candidate for candidate in candidates}
    return tuple(sorted(by_id.values(), key=_source_sort_key))


def _group_by_scope_and_kind(
    candidates: tuple[MemoryConsolidationSourceCandidate, ...],
) -> tuple[tuple[MemoryConsolidationSourceCandidate, ...], ...]:
    groups: dict[
        tuple[str | None, str | None, str | None, str],
        list[MemoryConsolidationSourceCandidate],
    ] = {}
    for candidate in candidates:
        key = (
            _optional_id(candidate.account_id),
            _optional_id(candidate.actor_id),
            _optional_id(candidate.space_id),
            candidate.kind.value,
        )
        groups.setdefault(key, []).append(candidate)
    return tuple(
        tuple(sorted(groups[group_key], key=_source_sort_key))
        for group_key in sorted(groups, key=_group_sort_key)
    )


def _build_group_result(
    group: tuple[MemoryConsolidationSourceCandidate, ...],
) -> MemoryConsolidationCandidate:
    source_ids = tuple(candidate.source_candidate_id for candidate in group)
    content_groups: dict[str, list[MemoryConsolidationSourceCandidate]] = {}
    for candidate in group:
        content_groups.setdefault(_normalize_text(candidate.text), []).append(candidate)
    if len(content_groups) == 1:
        proposed = max(group, key=_quality_key)
        decision = (
            MemoryConsolidationDecisionKind.DUPLICATE
            if len(group) > 1
            else MemoryConsolidationDecisionKind.RETAINED
        )
        reason = (
            "normalized duplicate candidates share one scoped memory"
            if decision is MemoryConsolidationDecisionKind.DUPLICATE
            else "candidate retained by deterministic consolidation"
        )
        supersedes: tuple[str, ...] = ()
        confidence = max(candidate.confidence for candidate in group)
    else:
        proposed = max(group, key=_newest_quality_key)
        supersedes = tuple(
            candidate.source_candidate_id
            for candidate in group
            if candidate.source_candidate_id != proposed.source_candidate_id
        )
        decision = MemoryConsolidationDecisionKind.CONFLICT
        reason = "scoped memory candidates have conflicting normalized content"
        confidence = min(candidate.confidence for candidate in group)
    result_id = _result_id(decision, source_ids)
    return MemoryConsolidationCandidate(
        candidate_id=result_id,
        proposed=proposed,
        decision_kind=decision,
        source_candidate_ids=source_ids,
        supersedes_candidate_ids=supersedes,
        confidence=confidence,
        reason=reason,
        metadata=immutable_metadata(
            {
                "decision": decision.value,
                "source_candidate_count": str(len(source_ids)),
                "superseded_candidate_count": str(len(supersedes)),
            }
        ),
    )


def _build_stale_result(
    candidate: MemoryConsolidationSourceCandidate,
) -> MemoryConsolidationCandidate:
    decision = MemoryConsolidationDecisionKind.STALE
    source_ids = (candidate.source_candidate_id,)
    return MemoryConsolidationCandidate(
        candidate_id=_result_id(decision, source_ids),
        proposed=candidate,
        decision_kind=decision,
        source_candidate_ids=source_ids,
        confidence=candidate.confidence,
        reason="candidate is older than the deterministic consolidation retention window",
        metadata=immutable_metadata(
            {
                "decision": decision.value,
                "source_candidate_count": "1",
                "superseded_candidate_count": "0",
            }
        ),
    )


def _quality_key(candidate: MemoryConsolidationSourceCandidate) -> tuple[float, str]:
    return candidate.confidence, candidate.source_candidate_id


def _newest_quality_key(
    candidate: MemoryConsolidationSourceCandidate,
) -> tuple[float, float, str]:
    return candidate.created_at.timestamp(), candidate.confidence, candidate.source_candidate_id


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in normalized
    )
    return " ".join(normalized.split())


def _optional_id(value: object | None) -> str | None:
    return None if value is None else str(value)


def _result_sort_key(result: MemoryConsolidationCandidate) -> str:
    return result.candidate_id


def _source_sort_key(candidate: MemoryConsolidationSourceCandidate) -> str:
    return candidate.source_candidate_id


def _group_sort_key(
    key: tuple[str | None, str | None, str | None, str],
) -> tuple[str, str, str, str]:
    return (
        key[0] or "",
        key[1] or "",
        key[2] or "",
        key[3],
    )


def _result_id(
    decision: MemoryConsolidationDecisionKind,
    source_ids: tuple[str, ...],
) -> str:
    material = "|".join((decision.value, *source_ids))
    return f"consolidation-{sha256(material.encode()).hexdigest()[:24]}"
