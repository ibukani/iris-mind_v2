"""Relationship store SQLAlchemy models."""

from __future__ import annotations

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from iris.adapters.persistence.sqlite.schema.base import Base


class RelationshipModel(Base):
    """SQLAlchemy model for relationship_snapshots."""

    __tablename__ = "relationship_snapshots"

    actor_id: Mapped[str] = mapped_column(String, primary_key=True)
    actor_label: Mapped[str | None] = mapped_column(String, nullable=True)
    affinity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    trust: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    familiarity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    relationship_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    source_observation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
