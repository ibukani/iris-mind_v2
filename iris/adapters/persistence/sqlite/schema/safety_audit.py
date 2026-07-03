"""SQLite safety audit schema contract。"""

from __future__ import annotations

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from iris.adapters.persistence.sqlite.schema.base import Base

SAFETY_AUDIT_TABLE = "safety_audit_records"
SAFETY_AUDIT_REQUIRED_COLUMNS = frozenset(
    {
        "audit_id",
        "observation_id",
        "occurred_at",
        "stage",
        "allowed",
        "reason",
        "risk_level",
        "source",
        "target_key",
        "policy",
        "policy_version",
        "retention_until",
    }
)
SAFETY_AUDIT_FORBIDDEN_RAW_CONTENT_COLUMNS = frozenset(
    {
        "text",
        "content",
        "body",
        "prompt",
        "output",
        "generated_output",
        "generated_text",
        "user_text",
        "raw_user_text",
        "generated_output_body",
    }
)


class SafetyAuditRecordModel(Base):
    """Raw content を持たない safety_audit_records の ORM model。"""

    __tablename__ = SAFETY_AUDIT_TABLE

    audit_id: Mapped[str] = mapped_column(String, primary_key=True)
    observation_id: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[str] = mapped_column(String, nullable=False)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    allowed: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    risk_level: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    target_key: Mapped[str] = mapped_column(String, nullable=False)
    policy: Mapped[str] = mapped_column(String, nullable=False)
    policy_version: Mapped[str] = mapped_column(String, nullable=False)
    retention_until: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index(
            "idx_safety_audit_target_stage_allowed_time",
            "target_key",
            "stage",
            "allowed",
            "occurred_at",
        ),
        Index("idx_safety_audit_occurred_at", "occurred_at"),
        Index("idx_safety_audit_retention", "retention_until"),
    )
