"""SQLite delivery user control schema contract。"""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from iris.adapters.persistence.sqlite.schema.base import Base

DELIVERY_USER_CONTROLS_TABLE = "delivery_user_controls"
DELIVERY_USER_CONTROLS_REQUIRED_COLUMNS = frozenset(
    {
        "target_key",
        "opt_out",
        "muted",
        "blocked",
        "interruptions_allowed",
        "updated_at",
    }
)
DELIVERY_USER_CONTROLS_FORBIDDEN_RAW_CONTENT_COLUMNS = frozenset(
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


class DeliveryUserControlModel(Base):
    """配送先ユーザー制御状態の ORM model。"""

    __tablename__ = DELIVERY_USER_CONTROLS_TABLE

    target_key: Mapped[str] = mapped_column(String, primary_key=True)
    opt_out: Mapped[int] = mapped_column(Integer, nullable=False)
    muted: Mapped[int] = mapped_column(Integer, nullable=False)
    blocked: Mapped[int] = mapped_column(Integer, nullable=False)
    interruptions_allowed: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
