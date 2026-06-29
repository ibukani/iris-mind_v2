"""Scheduler target SQLAlchemy models."""

from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from iris.adapters.persistence.sqlite.schema.base import Base


class SchedulerTargetModel(Base):
    """SchedulerTargetのORMモデル."""

    __tablename__ = "scheduler_targets"

    provider: Mapped[str] = mapped_column(primary_key=True)
    provider_subject: Mapped[str] = mapped_column(primary_key=True)
    provider_space_ref: Mapped[str] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(primary_key=True)
    actor_id: Mapped[str | None]
    account_id: Mapped[str | None]
    space_id: Mapped[str | None]
    display_name: Mapped[str | None]
    last_observed_at: Mapped[str]
    last_scheduler_attempt_at: Mapped[str | None]
    stale_after: Mapped[str | None]
    route_display_name: Mapped[str | None]
