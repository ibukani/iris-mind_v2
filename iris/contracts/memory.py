"""メモリ保存・検索の型付き契約。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
import hashlib
from typing import TYPE_CHECKING, NewType, Protocol, override, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.metadata import ImmutableMetadata
from iris.core.ids import ActorId, ObservationId, SpaceId
from iris.core.metadata import immutable_metadata

if TYPE_CHECKING:
    from collections.abc import Sequence

MemoryId = NewType("MemoryId", str)


class VectorMemoryIndexError(RuntimeError):
    """派生 vector index の操作失敗。"""


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
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


def memory_record_digest(record: MemoryRecord) -> str:
    """Vector entry の鮮度判定用 digest を返す。

    Returns:
        SHA-256 digest。
    """
    payload = record.model_dump_json()
    return hashlib.sha256(payload.encode()).hexdigest()


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


class VectorMemorySearchFilter(BaseModel):
    """VectorMemoryIndex へ渡す検索前フィルタ。"""

    model_config = ConfigDict(frozen=True)

    actor_id: ActorId | None = None
    space_id: SpaceId | None = None
    kind: MemoryKind | None = None
    include_archived: bool = False


class VectorMemoryEntry(BaseModel):
    """正本メモリから派生したベクトル index entry。"""

    model_config = ConfigDict(frozen=True)

    memory_id: MemoryId
    vector: tuple[float, ...]
    source_digest: str
    embedding_provider: str
    embedding_model: str
    embedding_dimension: int
    actor_id: ActorId | None = None
    space_id: SpaceId | None = None
    kind: MemoryKind = MemoryKind.NOTE
    archived: bool = False
    source_observation_id: ObservationId | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


def vector_memory_entry_from_record(
    record: MemoryRecord,
    *,
    vector: Sequence[float],
    embedding_provider: str,
    embedding_model: str,
    embedding_dimension: int,
) -> VectorMemoryEntry:
    """正本 MemoryRecord から canonical metadata 付き index entry を作る。

    Returns:
        VectorMemoryEntry: 派生 vector index 用 entry。
    """
    return VectorMemoryEntry(
        memory_id=record.id,
        vector=tuple(vector),
        source_digest=memory_record_digest(record),
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        actor_id=record.actor_id,
        space_id=record.space_id,
        kind=record.kind,
        archived=record.archived,
        source_observation_id=record.source_observation_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        metadata=record.metadata,
    )


class VectorMemoryEntryMetadata(BaseModel):
    """entry の鮮度・互換性判定に必要な metadata。"""

    model_config = ConfigDict(frozen=True)

    memory_id: MemoryId
    source_digest: str
    embedding_provider: str
    embedding_model: str
    embedding_dimension: int
    actor_id: ActorId | None = None
    space_id: SpaceId | None = None
    kind: MemoryKind = MemoryKind.NOTE
    archived: bool = False
    source_observation_id: ObservationId | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class VectorMemoryIndex(Protocol):
    """ベクトルベースのメモリ検索インデックスのプロトコル。

    semantic search のための軽量境界。正本ストアではなく
    検索インデックスとして動作する。
    """

    def upsert(self, entry: VectorMemoryEntry) -> None:
        """派生 index entry を登録または更新する。"""
        ...

    def delete(self, memory_id: MemoryId) -> None:
        """指定 ID のエントリをインデックスから削除する。"""
        ...

    def search(
        self,
        query_vector: Sequence[float],
        *,
        limit: int,
        filters: VectorMemorySearchFilter | None = None,
    ) -> Sequence[VectorMemorySearchResult]:
        """クエリベクトルに対する類似度検索を実行する。

        Args:
            query_vector: 検索クエリベクトル。
            limit: 返す結果の最大件数。
            filters: actor / space / kind / archived の検索前フィルタ。

        Returns:
            Sequence[VectorMemorySearchResult]: 類似度スコア降順の結果。
        """
        ...

    def metadata(self, memory_id: MemoryId) -> VectorMemoryEntryMetadata | None:
        """Entry metadata を返す。存在しない場合は None。"""
        ...

    def ids(self) -> Sequence[MemoryId]:
        """Index に存在する全 memory id を返す。"""
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
        """スコープ/種別/アーカイブ状態でフィルタしたレコードを返す。

        ``text`` と ``limit`` は text search 用であり、filter 実装は無視する。
        """
        ...
