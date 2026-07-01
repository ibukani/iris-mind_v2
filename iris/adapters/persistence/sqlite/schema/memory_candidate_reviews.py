"""SQLite memory_candidate_reviews schema contract。"""

from __future__ import annotations

MEMORY_CANDIDATE_REVIEWS_TABLE = "memory_candidate_reviews"
MEMORY_CANDIDATE_REVIEW_REQUIRED_COLUMNS = frozenset(
    {
        "candidate_id",
        "idempotency_key",
        "status",
        "candidate_json",
        "candidate_text",
        "candidate_kind",
        "candidate_source",
        "candidate_reason",
        "candidate_confidence",
        "candidate_salience",
        "candidate_retention_policy",
        "candidate_sensitivity",
        "candidate_review_required",
        "actor_id",
        "account_id",
        "space_id",
        "source_observation_id",
        "reviewed_at",
        "reviewed_by",
        "review_reason",
        "promoted_memory_id",
        "metadata_json",
        "created_at",
        "updated_at",
    }
)
