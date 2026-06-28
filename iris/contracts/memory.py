"""メモリ保存・検索の型付き契約。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from typing import NewType, Protocol, override, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from iris.core.ids import ActorId, ObservationId, SpaceId
from iris.core.metadata import EMPTY_METADATA, immutable_metadata

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


class MemoryRecord(BaseModel):
    """単一のメモリレコード。"""

    model_config = ConfigDict(frozen=True)

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
    metadata: Mapping[str, str] = Field(default_factory=dict)

    def model_post_init(self, __context: object) -> None:
        """メタデータを不変な mapping proxy として防御的にコピーする。"""
        if self.metadata is not EMPTY_METADATA:
            object.__setattr__(self, "metadata", immutable_metadata(self.metadata))


class MemoryQuery(BaseModel):
    """メモリレコード検索のクエリ。"""

    model_config = ConfigDict(frozen=True)

    text: str
    actor_id: ActorId | None = None
    space_id: SpaceId | None = None
    limit: int = 5
    kind: MemoryKind | None = None
    include_archived: bool = False


class MemorySearchResult(BaseModel):
    """関連性スコア付きのメモリレコード。"""

    model_config = ConfigDict(frozen=True)

    record: MemoryRecord
    score: float


class VectorMemorySearchResult(BaseModel):
    """ベクトル類似度スコア付きのメモリ検索結果。"""

    model_config = ConfigDict(frozen=True)

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
