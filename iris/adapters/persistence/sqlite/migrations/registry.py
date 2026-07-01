"""SQLite migration registry。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.persistence.sqlite.migrations.v0001_baseline import BASELINE_V1

if TYPE_CHECKING:
    from iris.adapters.persistence.sqlite.migrator_types import SQLiteMigration


def available_migrations() -> tuple[SQLiteMigration, ...]:
    """適用順に並んだ migration 定義を返す。

    Returns:
        tuple[SQLiteMigration, ...]: version 昇順の migration 定義。
    """
    return (BASELINE_V1,)
