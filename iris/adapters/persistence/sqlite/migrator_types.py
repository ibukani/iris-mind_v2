"""SQLite migrator の型定義。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib


@dataclass(frozen=True)
class SQLiteMigration:
    """単一 SQLite migration 定義。"""

    version: int
    name: str
    statements: tuple[str, ...]

    @property
    def checksum(self) -> str:
        """Migration 定義の安定 checksum を返す。"""
        payload = "\n-- statement --\n".join((self.name, *self.statements))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
