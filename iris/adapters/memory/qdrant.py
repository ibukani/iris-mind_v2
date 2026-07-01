"""Qdrant を使う永続 VectorMemoryIndex adapter。"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar, override
import uuid

import httpx
from pydantic import BaseModel, ConfigDict

from iris.contracts.memory import (
    MemoryId,
    VectorMemoryEntry,
    VectorMemoryEntryMetadata,
    VectorMemoryIndex,
    VectorMemoryIndexError,
    VectorMemorySearchResult,
)

_HTTP_NOT_FOUND = 404
_ResponseModel = TypeVar("_ResponseModel", bound=BaseModel)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


class _PointPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    memory_id: str
    source_digest: str
    embedding_model: str
    embedding_dimension: int


class _ScoredPoint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    score: float
    payload: _PointPayload


class _QueryResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    points: tuple[_ScoredPoint, ...] = ()


class _QueryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    result: _QueryResult


class _Point(BaseModel):
    model_config = ConfigDict(extra="ignore")

    payload: _PointPayload


class _PointResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    result: _Point | None


class _ScrollResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    points: tuple[_Point, ...] = ()
    next_page_offset: str | int | None = None


class _ScrollResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    result: _ScrollResult


class QdrantVectorMemoryIndex(VectorMemoryIndex):
    """Qdrant collection を派生検索 index として扱う adapter。"""

    def __init__(
        self,
        *,
        url: str,
        collection: str,
        dimension: int,
        api_key: str | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        """接続先と collection 設定で初期化する。"""
        headers = {"api-key": api_key} if api_key is not None else None
        self._client = client or httpx.Client(
            base_url=url.rstrip("/"), headers=headers, timeout=timeout_seconds
        )
        self._owns_client = client is None
        self._collection = collection
        self._dimension = dimension
        self._ensure_collection()

    def close(self) -> None:
        """所有する HTTP client を閉じる。"""
        if self._owns_client:
            self._client.close()

    def _ensure_collection(self) -> None:
        response = self._send(
            lambda: self._client.get(f"/collections/{self._collection}"),
            "ensure collection",
        )
        if response.status_code == _HTTP_NOT_FOUND:
            response = self._send(
                lambda: self._client.put(
                    f"/collections/{self._collection}",
                    json={"vectors": {"size": self._dimension, "distance": "Cosine"}},
                ),
                "create collection",
            )
        self._raise_for_status(response, "ensure collection")

    @staticmethod
    def _point_id(memory_id: MemoryId) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"iris-memory:{memory_id}"))

    @staticmethod
    def _raise_for_status(response: httpx.Response, operation: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"Qdrant {operation} failed: HTTP {response.status_code}"
            raise VectorMemoryIndexError(msg) from exc

    @staticmethod
    def _send(request: Callable[[], httpx.Response], operation: str) -> httpx.Response:
        try:
            return request()
        except httpx.HTTPError as exc:
            msg = f"Qdrant {operation} failed: {exc.__class__.__name__}"
            raise VectorMemoryIndexError(msg) from exc

    @staticmethod
    def _parse_response(
        response: httpx.Response,
        model: type[_ResponseModel],
        operation: str,
    ) -> _ResponseModel:
        try:
            return model.model_validate_json(response.content)
        except ValueError as exc:
            msg = f"Qdrant {operation} returned an invalid response"
            raise VectorMemoryIndexError(msg) from exc

    @override
    def upsert(self, entry: VectorMemoryEntry) -> None:
        """Entry を collection に upsert する。

        Raises:
            VectorMemoryIndexError: 通信失敗または次元不一致の場合。
        """
        if len(entry.vector) != self._dimension or entry.embedding_dimension != self._dimension:
            msg = "Qdrant vector dimension does not match collection"
            raise VectorMemoryIndexError(msg)
        payload = {
            "memory_id": str(entry.memory_id),
            "source_digest": entry.source_digest,
            "embedding_model": entry.embedding_model,
            "embedding_dimension": entry.embedding_dimension,
            "metadata": dict(entry.metadata),
        }
        response = self._send(
            lambda: self._client.put(
                f"/collections/{self._collection}/points",
                params={"wait": "true"},
                json={
                    "points": [
                        {
                            "id": self._point_id(entry.memory_id),
                            "vector": list(entry.vector),
                            "payload": payload,
                        }
                    ]
                },
            ),
            "upsert",
        )
        self._raise_for_status(response, "upsert")

    @override
    def delete(self, memory_id: MemoryId) -> None:
        """Memory id に対応する point を削除する。"""
        response = self._send(
            lambda: self._client.post(
                f"/collections/{self._collection}/points/delete",
                params={"wait": "true"},
                json={"points": [self._point_id(memory_id)]},
            ),
            "delete",
        )
        self._raise_for_status(response, "delete")

    @override
    def search(
        self, query_vector: Sequence[float], *, limit: int
    ) -> Sequence[VectorMemorySearchResult]:
        """Qdrant query API で類似 point を返す。

        Returns:
            類似度降順の検索結果。

        Raises:
            VectorMemoryIndexError: 次元不一致、通信失敗、応答不正の場合。
        """
        if limit <= 0:
            return ()
        if len(query_vector) != self._dimension:
            msg = "Qdrant query vector dimension does not match collection"
            raise VectorMemoryIndexError(msg)
        response = self._send(
            lambda: self._client.post(
                f"/collections/{self._collection}/points/query",
                json={"query": list(query_vector), "limit": limit, "with_payload": True},
            ),
            "query",
        )
        self._raise_for_status(response, "query")
        parsed = self._parse_response(response, _QueryResponse, "query")
        return tuple(
            VectorMemorySearchResult(memory_id=MemoryId(point.payload.memory_id), score=point.score)
            for point in parsed.result.points
        )

    @override
    def metadata(self, memory_id: MemoryId) -> VectorMemoryEntryMetadata | None:
        """Point payload から compatibility metadata を返す。

        Returns:
            Entry metadata。未登録時は None。
        """
        response = self._send(
            lambda: self._client.get(
                f"/collections/{self._collection}/points/{self._point_id(memory_id)}"
            ),
            "get point",
        )
        if response.status_code == _HTTP_NOT_FOUND:
            return None
        self._raise_for_status(response, "get point")
        point = self._parse_response(response, _PointResponse, "get point").result
        if point is None:
            return None
        payload = point.payload
        return VectorMemoryEntryMetadata(
            memory_id=MemoryId(payload.memory_id),
            source_digest=payload.source_digest,
            embedding_model=payload.embedding_model,
            embedding_dimension=payload.embedding_dimension,
        )

    @override
    def ids(self) -> Sequence[MemoryId]:
        """Scroll API で全 memory id を列挙する。

        Returns:
            登録済み memory id。
        """
        ids: list[MemoryId] = []
        offset: str | int | None = None
        while True:
            body: dict[str, object] = {"limit": 256, "with_payload": True}
            if offset is not None:
                body["offset"] = offset
            response = self._post_scroll(body)
            self._raise_for_status(response, "scroll")
            result = self._parse_response(response, _ScrollResponse, "scroll").result
            ids.extend(MemoryId(point.payload.memory_id) for point in result.points)
            offset = result.next_page_offset
            if offset is None:
                return tuple(ids)

    def _post_scroll(self, body: dict[str, object]) -> httpx.Response:
        """Scroll request を transport error contract へ正規化する。

        Returns:
            Qdrant response。
        """
        return self._send(
            lambda: self._client.post(f"/collections/{self._collection}/points/scroll", json=body),
            "scroll",
        )
