"""SQLAlchemy model for accounts."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from iris.adapters.sqlite.models.base import Base

if TYPE_CHECKING:
    from collections.abc import Mapping


class AccountModel(Base):
    """SQLAlchemy model for the accounts table."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subject", name="uq_accounts_provider_subject"),
    )

    account_id: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    provider_subject: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    linked_actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_json: Mapped[str] = mapped_column(String, nullable=False, default="{}")

    @property
    def metadata_dict(self) -> Mapping[str, str]:
        """Parse metadata JSON string to dict."""
        if not self.metadata_json:
            return {}

        parsed = json.loads(self.metadata_json)
        result: dict[str, str] = dict(parsed)
        return result
