"""Implicit memory candidate の共有検証規則。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.contracts.memory_candidates import MemoryCandidateSource, MemoryRetentionPolicy

if TYPE_CHECKING:
    from iris.contracts.memory_candidates import MemoryCandidate


def candidate_content_is_valid(
    candidate: MemoryCandidate,
    *,
    text: str,
    min_confidence: float,
    max_text_length: int,
) -> bool:
    """候補本文と confidence が policy 境界内か判定する。

    Returns:
        本文が空でなく、長さと confidence が許容範囲なら True。
    """
    return bool(text) and len(text) <= max_text_length and candidate.confidence >= min_confidence


def implicit_review_provenance_is_valid(candidate: MemoryCandidate) -> bool:
    """候補が implicit conversation の review-required 経路由来か判定する。

    Returns:
        source、retention policy、review flag がすべて正規値なら True。
    """
    return (
        candidate.source
        in {
            MemoryCandidateSource.IMPLICIT_CONVERSATION,
            MemoryCandidateSource.CONSOLIDATION,
        }
        and candidate.retention_policy is MemoryRetentionPolicy.REVIEW_REQUIRED
        and candidate.review_required
    )
