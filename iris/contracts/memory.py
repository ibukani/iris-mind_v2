"""メモリ保存・検索の型付き契約。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, NewType

if TYPE_CHECKING:
    from iris.core.ids import UserId

MemoryId = NewType("MemoryId", str)


@dataclass(frozen=True)
class MemoryRecord:
    """単一のメモリレコード。"""

    id: MemoryId
    text: str
    subject_id: UserId | None = None
    salience: float = 0.0


@dataclass(frozen=True)
class MemoryQuery:
    """メモリレコード検索のクエリ。"""

    text: str
    subject_id: UserId | None = None
    limit: int = 5


@dataclass(frozen=True)
class MemorySearchResult:
    """関連性スコア付きのメモリレコード。"""

    record: MemoryRecord
    score: float
