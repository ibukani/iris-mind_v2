"""Affect baseline SQLAlchemy models."""

from __future__ import annotations

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from iris.adapters.sqlite.models.base import Base


class AffectModel(Base):
    """SQLAlchemy model for affect_baselines."""

    __tablename__ = "affect_baselines"

    owner_key: Mapped[str] = mapped_column(String, primary_key=True)
    scope: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    mood_label: Mapped[str | None] = mapped_column(String, nullable=True)
    valence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    arousal: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dominance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    affect_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    source_observation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
