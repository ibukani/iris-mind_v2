"""Activity events SQLAlchemy models."""

from __future__ import annotations

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from iris.adapters.sqlite.models.base import Base


class ActivityEventModel(Base):
    """SQLAlchemy model for activity_events."""

    __tablename__ = "activity_events"

    activity_id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    provider_event_id: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    space_id: Mapped[str | None] = mapped_column(String, nullable=True)
    activity_kind: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[str] = mapped_column(String, nullable=False)
    received_at: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index(
            "idx_activity_events_provider_event",
            "source",
            "provider_event_id",
            unique=True,
            sqlite_where=text("source IS NOT NULL AND provider_event_id IS NOT NULL"),
        ),
        Index("idx_activity_events_occurred_at", "occurred_at"),
    )
