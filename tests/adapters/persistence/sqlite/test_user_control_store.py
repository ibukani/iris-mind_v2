"""SQLite delivery user control store tests。"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
import sqlite3
from typing import TYPE_CHECKING

import pytest

from iris.adapters.persistence.sqlite.schema.user_control import (
    DELIVERY_USER_CONTROLS_FORBIDDEN_RAW_CONTENT_COLUMNS,
)
from iris.adapters.persistence.sqlite.stores.user_control import SQLiteDeliveryUserControlStore
from iris.contracts.user_control import UserControlState

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.anyio
_NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
_TARGET_KEY = "discord:user-1:space-1"


async def test_sqlite_user_control_roundtrip_and_update(tmp_path: Path) -> None:
    """Set / get の roundtrip と上書き更新を検証する。"""
    db_path = tmp_path / "state.sqlite3"
    store = SQLiteDeliveryUserControlStore(db_path)
    assert await store.get(_TARGET_KEY) is None

    first = UserControlState(opt_out=False, muted=True, updated_at=_NOW)
    await store.set(_TARGET_KEY, first)
    assert await store.get(_TARGET_KEY) == first

    second = UserControlState(opt_out=True, blocked=True, updated_at=_NOW)
    await store.set(_TARGET_KEY, second)
    assert await store.get(_TARGET_KEY) == second
    await store.close()


async def test_sqlite_user_control_survives_restart(tmp_path: Path) -> None:
    """SQLite backend は restart 後も制御状態を保持する。"""
    db_path = tmp_path / "state.sqlite3"
    store = SQLiteDeliveryUserControlStore(db_path)
    await store.set(
        _TARGET_KEY,
        UserControlState(opt_out=True, updated_at=_NOW),
    )
    await store.close()

    reopened = SQLiteDeliveryUserControlStore(db_path)
    try:
        state = await reopened.get(_TARGET_KEY)
        assert state is not None
        assert state.opt_out is True
        assert state.interruptions_allowed is True
    finally:
        await reopened.close()


async def test_sqlite_user_control_schema_does_not_store_raw_content(tmp_path: Path) -> None:
    """User control schema は raw content 用 column を持たない。"""
    db_path = tmp_path / "state.sqlite3"
    store = SQLiteDeliveryUserControlStore(db_path)
    await store.set(_TARGET_KEY, UserControlState(muted=True, updated_at=_NOW))
    await store.close()

    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute("PRAGMA table_info(delivery_user_controls)").fetchall()
        columns = {str(row[1]) for row in rows}

    assert columns.isdisjoint(DELIVERY_USER_CONTROLS_FORBIDDEN_RAW_CONTENT_COLUMNS)
