"""SQLite SpaceBindingStore implementation."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING, cast, override

from iris.adapters.app_gateway.ports import SpaceBindingStore
from iris.contracts.spaces import SpaceBinding, SpaceBindingStoreError, SpaceKind
from iris.core.ids import ExternalRef, SpaceId

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping


class SQLiteSpaceBindingStore(SpaceBindingStore):
    """SQLite-backed store for external space bindings."""

    def __init__(self, db_path: str | Path) -> None:
        """Create a SQLite-backed store.

        Args:
            db_path: SQLite database path.
        """
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @override
    async def get_by_external_ref(
        self,
        *,
        provider: str,
        provider_space_ref: ExternalRef,
    ) -> SpaceBinding | None:
        """Get a binding by provider and external space ref.

        Returns:
            Stored binding, or ``None``.
        """
        query = "SELECT * FROM space_bindings WHERE provider = ? AND provider_space_ref = ?"
        with self._closing_connection() as conn:
            row = conn.execute(query, (provider, str(provider_space_ref))).fetchone()
        return _row_to_binding(row) if row is not None else None

    @override
    async def put(self, binding: SpaceBinding) -> SpaceBinding:
        """Create or update a binding.

        Returns:
            Stored binding.

        Raises:
            SpaceBindingStoreError: If ``space_id`` is reused by another external ref.
        """
        with self._transaction() as conn:
            self._raise_on_space_id_conflict(conn, binding)
            conn.execute(
                """
                INSERT INTO space_bindings (
                    provider,
                    provider_space_ref,
                    space_id,
                    display_name,
                    space_kind,
                    metadata_json,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(provider, provider_space_ref) DO UPDATE SET
                    space_id = excluded.space_id,
                    display_name = excluded.display_name,
                    space_kind = excluded.space_kind,
                    metadata_json = excluded.metadata_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    binding.provider,
                    str(binding.provider_space_ref),
                    str(binding.space_id),
                    binding.display_name,
                    binding.space_kind.value,
                    _metadata_to_json(binding.metadata),
                ),
            )
            row = conn.execute(
                "SELECT * FROM space_bindings WHERE provider = ? AND provider_space_ref = ?",
                (binding.provider, str(binding.provider_space_ref)),
            ).fetchone()
        if row is None:
            message = "space binding write did not return a row"
            raise SpaceBindingStoreError(message)
        return _row_to_binding(row)

    def _init_db(self) -> None:
        query = """
            CREATE TABLE IF NOT EXISTS space_bindings (
                provider TEXT NOT NULL,
                provider_space_ref TEXT NOT NULL,
                space_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                space_kind TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (provider, provider_space_ref),
                UNIQUE(space_id)
            )
        """
        with self._closing_connection() as conn:
            conn.execute(query)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _closing_connection(self) -> Generator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _raise_on_space_id_conflict(
        conn: sqlite3.Connection,
        binding: SpaceBinding,
    ) -> None:
        row = conn.execute(
            "SELECT provider, provider_space_ref FROM space_bindings WHERE space_id = ?",
            (str(binding.space_id),),
        ).fetchone()
        if row is None:
            return
        same_ref = row["provider"] == binding.provider and row["provider_space_ref"] == str(
            binding.provider_space_ref
        )
        if same_ref:
            return
        message = f"space_id conflict: {binding.space_id}"
        raise SpaceBindingStoreError(message)


def _row_to_binding(row: sqlite3.Row) -> SpaceBinding:
    return SpaceBinding(
        space_id=SpaceId(cast("str", row["space_id"])),
        provider=cast("str", row["provider"]),
        provider_space_ref=ExternalRef(cast("str", row["provider_space_ref"])),
        display_name=cast("str", row["display_name"]),
        space_kind=SpaceKind(cast("str", row["space_kind"])),
        metadata=_metadata_from_json(cast("str", row["metadata_json"])),
    )


def _metadata_to_json(metadata: Mapping[str, str]) -> str:
    return json.dumps(dict(metadata), sort_keys=True)


def _metadata_from_json(raw_value: str) -> Mapping[str, str]:
    loaded: object = json.loads(raw_value)
    if not isinstance(loaded, dict):
        message = "space binding metadata_json must be an object"
        raise SpaceBindingStoreError(message)
    loaded_items = cast("dict[object, object]", loaded)
    metadata: dict[str, str] = {}
    for key, value in loaded_items.items():
        if not isinstance(key, str) or not isinstance(value, str):
            message = "space binding metadata_json values must be strings"
            raise SpaceBindingStoreError(message)
        metadata[key] = value
    return metadata
