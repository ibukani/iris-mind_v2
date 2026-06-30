"""Delivery Outbox SQLAlchemy models."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from iris.adapters.persistence.sqlite.schema.base import Base


class DeliveryOutboxModel(Base):
    """SQLAlchemy model for delivery_outbox."""

    __tablename__ = "delivery_outbox"

    delivery_id: Mapped[str] = mapped_column(String, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    not_before: Mapped[str | None] = mapped_column(String, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_id: Mapped[str | None] = mapped_column(String, nullable=True)
    lease_expires_at: Mapped[str | None] = mapped_column(String, nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    source_observation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    target_provider: Mapped[str] = mapped_column(String, nullable=False)
    target_provider_subject: Mapped[str | None] = mapped_column(String, nullable=True)
    target_provider_space_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    target_session_id: Mapped[str] = mapped_column(String, nullable=False)
    target_actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    target_account_id: Mapped[str | None] = mapped_column(String, nullable=True)
    target_space_id: Mapped[str | None] = mapped_column(String, nullable=True)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    action_id: Mapped[str] = mapped_column(String, nullable=False)
    action_session_id: Mapped[str] = mapped_column(String, nullable=False)
    action_correlation_id: Mapped[str] = mapped_column(String, nullable=False)
    action_text: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index(
            "delivery_outbox_due_idx",
            "target_provider",
            "status",
            "created_at",
            "delivery_id",
        ),
    )


class DeliveryReportFingerprintModel(Base):
    """SQLAlchemy model for delivery_report_fingerprints."""

    __tablename__ = "delivery_report_fingerprints"

    fingerprint_key: Mapped[str] = mapped_column(String, primary_key=True)
    delivery_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("delivery_outbox.delivery_id", ondelete="CASCADE"),
        nullable=False,
    )
    lease_id: Mapped[str | None] = mapped_column(String, nullable=True)
    action_id: Mapped[str] = mapped_column(String, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    external_message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    error_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index(
            "delivery_report_lease_idx",
            "delivery_id",
            "lease_id",
        ),
    )
