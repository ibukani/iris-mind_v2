"""SQLite 永続化 adapter の SQLAlchemy schema。"""

from __future__ import annotations

from iris.adapters.persistence.sqlite.schema.account import AccountModel
from iris.adapters.persistence.sqlite.schema.activity import ActivityEventModel
from iris.adapters.persistence.sqlite.schema.affect import AffectModel
from iris.adapters.persistence.sqlite.schema.base import Base
from iris.adapters.persistence.sqlite.schema.delivery import (
    DeliveryOutboxModel,
    DeliveryReportFingerprintModel,
)
from iris.adapters.persistence.sqlite.schema.relationship import RelationshipModel
from iris.adapters.persistence.sqlite.schema.scheduler_target import SchedulerTargetModel

__all__ = [
    "AccountModel",
    "ActivityEventModel",
    "AffectModel",
    "Base",
    "DeliveryOutboxModel",
    "DeliveryReportFingerprintModel",
    "RelationshipModel",
    "SchedulerTargetModel",
]
