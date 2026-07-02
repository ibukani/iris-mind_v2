"""SQLite migration registry。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.persistence.sqlite.migrations.v0001_baseline import BASELINE_V1
from iris.adapters.persistence.sqlite.migrations.v0002_runtime_learning_state import (
    RUNTIME_LEARNING_STATE_V2,
)
from iris.adapters.persistence.sqlite.migrations.v0003_conversation_transcripts import (
    CONVERSATION_TRANSCRIPTS_V3,
)

if TYPE_CHECKING:
    from iris.adapters.persistence.sqlite.migrator_types import SQLiteMigration


def available_migrations() -> tuple[SQLiteMigration, ...]:
    """適用順に並んだ migration 定義を返す。

    Returns:
        tuple[SQLiteMigration, ...]: version 昇順の migration 定義。
    """
    return (BASELINE_V1, RUNTIME_LEARNING_STATE_V2, CONVERSATION_TRANSCRIPTS_V3)
