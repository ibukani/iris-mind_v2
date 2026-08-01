"""SQLite-backed durable DeliveryUserControlStore implementation。"""

from __future__ import annotations

from typing import override

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from iris.adapters.persistence.sqlite.context import (
    SQLiteDatabaseInput,
    resolve_database_manager,
)
from iris.adapters.persistence.sqlite.schema.user_control import DeliveryUserControlModel
from iris.adapters.persistence.sqlite.serialization import (
    required_datetime_to_text,
    text_to_datetime,
)
from iris.contracts.user_control import DeliveryUserControlStore, UserControlState

_BOOLEAN_ONE = 1


class SQLiteDeliveryUserControlStore(DeliveryUserControlStore):
    """SQLite-backed durable delivery user control store。"""

    def __init__(self, db: SQLiteDatabaseInput) -> None:
        """SQLite user control store を作成する。"""
        self._db = resolve_database_manager(db)

    @override
    async def get(self, target_key: str) -> UserControlState | None:
        """Target の制御状態を返す。

        Returns:
            保存済み状態。未保存なら None。
        """
        async with self._db.transaction() as session:
            model = await session.scalar(
                select(DeliveryUserControlModel).where(
                    DeliveryUserControlModel.target_key == target_key,
                )
            )
        if model is None:
            return None
        return UserControlState(
            opt_out=_to_bool(model.opt_out),
            muted=_to_bool(model.muted),
            blocked=_to_bool(model.blocked),
            interruptions_allowed=_to_bool(model.interruptions_allowed),
            updated_at=text_to_datetime(str(model.updated_at)),
        )

    @override
    async def set(self, target_key: str, state: UserControlState) -> None:
        """Target の制御状態を保存する。"""
        stmt = insert(DeliveryUserControlModel).values(
            target_key=target_key,
            opt_out=_to_int(value=state.opt_out),
            muted=_to_int(value=state.muted),
            blocked=_to_int(value=state.blocked),
            interruptions_allowed=_to_int(value=state.interruptions_allowed),
            updated_at=required_datetime_to_text(state.updated_at),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["target_key"],
            set_={
                "opt_out": stmt.excluded.opt_out,
                "muted": stmt.excluded.muted,
                "blocked": stmt.excluded.blocked,
                "interruptions_allowed": stmt.excluded.interruptions_allowed,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        async with self._db.transaction() as session:
            await session.execute(stmt)

    async def close(self) -> None:
        """Underlying SQLite engine を閉じる。"""
        await self._db.close()


def _to_bool(value: int) -> bool:
    return value == _BOOLEAN_ONE


def _to_int(*, value: bool) -> int:
    return _BOOLEAN_ONE if value else 0
