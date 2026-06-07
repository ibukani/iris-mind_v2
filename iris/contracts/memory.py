"""メモリ保存・検索の型付き契約。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, NewType, Protocol, override, runtime_checkable

from iris.core.metadata import EMPTY_METADATA, immutable_metadata

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from iris.core.ids import ActorId, ObservationId, SpaceId

MemoryId = NewType("MemoryId", str)


class MemoryKind(StrEnum):
    """メモリレコードの種別。

    ``RELATIONSHIP_EVENT`` は関係状態 (affinity/trust/familiarity) ではなく、
    関係に関わる出来事・記憶のサマリを表す。RelationshipSnapshot の永続化
    には ``IrisApp`` 側で別のストレージを使う想定。
    """

    EPISODE = "episode"
    PREFERENCE = "preference"
    FACT = "fact"
    RELATIONSHIP_EVENT = "relationship_event"
    TASK = "task"
    NOTE = "note"


@dataclass(frozen=True)
class MemoryRecord:
    """単一のメモリレコード。"""

    id: MemoryId
    text: str
    actor_id: ActorId | None = None
    space_id: SpaceId | None = None
    salience: float = 0.0
    kind: MemoryKind = MemoryKind.NOTE
    confidence: float = 1.0
    source_observation_id: ObservationId | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived: bool = False
    metadata: Mapping[str, str] = EMPTY_METADATA

    def __post_init__(self) -> None:
        """メタデータを不変な mapping proxy として防御的にコピーする。"""
        object.__setattr__(self, "metadata", immutable_metadata(self.metadata))


@dataclass(frozen=True)
class MemoryQuery:
    """メモリレコード検索のクエリ。"""

    text: str
    actor_id: ActorId | None = None
    space_id: SpaceId | None = None
    limit: int = 5
    kind: MemoryKind | None = None
    include_archived: bool = False


@dataclass(frozen=True)
class MemorySearchResult:
    """関連性スコア付きのメモリレコード。"""

    record: MemoryRecord
    score: float


@dataclass(frozen=True)
class VectorMemorySearchResult:
    """ベクトル類似度スコア付きのメモリ検索結果。"""

    memory_id: MemoryId
    score: float


class VectorMemoryIndex(Protocol):
    """ベクトルベースのメモリ検索インデックスのプロトコル。

    semantic search のための軽量境界。正本ストアではなく
    検索インデックスとして動作する。
    """

    def upsert(self, memory_id: MemoryId, text: str, metadata: Mapping[str, str]) -> None:
        """メモリテキストとメタデータをインデックスに登録または更新する。"""
        ...

    def delete(self, memory_id: MemoryId) -> None:
        """指定 ID のエントリをインデックスから削除する。"""
        ...

    def search(self, query: str, *, limit: int) -> Sequence[VectorMemorySearchResult]:
        """クエリテキストに対するベクトル類似度検索を実行する。

        Args:
            query: 検索クエリテキスト。
            limit: 返す結果の最大件数。

        Returns:
            Sequence[VectorMemorySearchResult]: 類似度スコア降順の結果。
        """
        ...


@runtime_checkable
class MemoryStore(Protocol):
    """メモリストレージバックエンドのプロトコル。

    検索/取得専用の最小契約。LangChain/ベクター型など書き込み API
    を持たない外部バックエンドの互換性のために維持される。
    """

    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        """クエリに一致するメモリレコードを検索する。"""
        ...

    def get(self, memory_id: MemoryId) -> MemoryRecord | None:
        """指定 ID のメモリレコードを返す。存在しない場合は None。"""
        ...

    def put(self, record: MemoryRecord) -> None:
        """メモリレコードを保存する。"""
        ...


@runtime_checkable
class MutableMemoryStore(MemoryStore, Protocol):
    """可変なメモリストレージバックエンドのプロトコル。

    永続化や更新が必要なバックエンドの完全な CRUD 契約。
    """

    @override
    def get(self, memory_id: MemoryId) -> MemoryRecord | None:
        """指定 ID のメモリレコードを返す。存在しない場合は None。"""
        ...

    def update(self, record: MemoryRecord) -> MemoryRecord:
        """既存レコードを upsert して正規化された状態を返す。"""
        ...

    def archive(self, memory_id: MemoryId, *, archived: bool = True) -> MemoryRecord | None:
        """指定 ID のアーカイブ状態を切り替えて、対象レコードを返す。"""
        ...

    def filter(self, query: MemoryQuery) -> Sequence[MemoryRecord]:
        """スコープ/種別/アーカイブ状態などでフィルタしたレコードを返す。"""
        ...
