"""SQLite review candidate type migration v4。"""

from __future__ import annotations

from iris.adapters.persistence.sqlite.migrator_types import SQLiteMigration

REVIEW_CANDIDATE_TYPE_V4 = SQLiteMigration(
    version=4,
    name="review_candidate_type",
    statements=(
        """
        ALTER TABLE memory_candidate_reviews
        ADD COLUMN candidate_type TEXT NOT NULL DEFAULT 'memory'
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_memory_candidate_reviews_type_status_created
        ON memory_candidate_reviews(candidate_type, status, created_at, candidate_id)
        """,
    ),
)
