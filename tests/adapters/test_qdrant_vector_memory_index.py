"""QdrantVectorMemoryIndex の network-free adapter test。"""

from __future__ import annotations

import json

import httpx
import pytest

from iris.adapters.embeddings.fake import DeterministicFakeEmbedding
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.memory.qdrant import QdrantVectorMemoryIndex
from iris.contracts.memory import (
    MemoryId,
    MemoryKind,
    MemoryRecord,
    VectorMemoryEntry,
    VectorMemoryIndexError,
    VectorMemorySearchFilter,
    memory_record_digest,
)
from iris.core.ids import ActorId, ObservationId, SpaceId
from iris.runtime.memory_vector_rebuilder import MemoryVectorIndexRebuilder


def _collection_info(size: int) -> dict[str, object]:
    return {"result": {"config": {"params": {"vectors": {"size": size, "distance": "Cosine"}}}}}


def test_qdrant_index_upsert_and_query_use_typed_payload() -> None:
    """REST payload が memory id と compatibility metadata を保持する。"""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"result": {}})
        if request.url.path.endswith("/points/query"):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "points": [
                            {
                                "score": 0.9,
                                "payload": {
                                    "memory_id": "m1",
                                    "source_digest": "digest",
                                    "embedding_provider": "fake",
                                    "embedding_model": "fake-v1",
                                    "embedding_dimension": 2,
                                },
                            }
                        ]
                    }
                },
            )
        return httpx.Response(200, json={"result": {"status": "ok"}})

    client = httpx.Client(base_url="http://qdrant.test", transport=httpx.MockTransport(handler))
    index = QdrantVectorMemoryIndex(
        url="http://unused.test", collection="memory", dimension=2, client=client
    )
    index.upsert(
        VectorMemoryEntry(
            memory_id=MemoryId("m1"),
            vector=(1.0, 0.0),
            source_digest="digest",
            embedding_provider="fake",
            embedding_model="fake-v1",
            embedding_dimension=2,
            actor_id=ActorId("actor-1"),
            space_id=SpaceId("space-1"),
            kind=MemoryKind.PREFERENCE,
            archived=False,
            source_observation_id=ObservationId("obs-1"),
        )
    )

    results = index.search(
        (1.0, 0.0),
        limit=1,
        filters=VectorMemorySearchFilter(
            actor_id=ActorId("actor-1"),
            space_id=SpaceId("space-1"),
            kind=MemoryKind.PREFERENCE,
        ),
    )

    assert results[0].memory_id == MemoryId("m1")
    assert [request.method for request in requests] == ["GET", "PUT", "POST"]

    upsert_body = json.loads(requests[1].content)
    payload = upsert_body["points"][0]["payload"]
    assert payload["memory_id"] == "m1"
    assert payload["embedding_provider"] == "fake"
    assert payload["embedding_model"] == "fake-v1"
    assert payload["embedding_dimension"] == 2
    assert payload["actor_id"] == "actor-1"
    assert payload["space_id"] == "space-1"
    assert payload["kind"] == "preference"
    assert payload["archived"] is False
    assert payload["source_observation_id"] == "obs-1"

    query_body = json.loads(requests[2].content)
    assert query_body["filter"] == {
        "must": [
            {"key": "actor_id", "match": {"value": "actor-1"}},
            {"key": "space_id", "match": {"value": "space-1"}},
            {"key": "kind", "match": {"value": "preference"}},
            {"key": "archived", "match": {"value": False}},
        ]
    }


def test_qdrant_index_rejects_incompatible_dimensions() -> None:
    """Collection と異なる entry/query dimension は provider call 前に拒否する。"""
    client = httpx.Client(
        base_url="http://qdrant.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"result": {}})),
    )
    index = QdrantVectorMemoryIndex(
        url="http://unused.test", collection="memory", dimension=2, client=client
    )
    entry = VectorMemoryEntry(
        memory_id=MemoryId("m1"),
        vector=(1.0, 0.0),
        source_digest="digest",
        embedding_provider="fake",
        embedding_model="fake-v1",
        embedding_dimension=3,
    )

    with pytest.raises(VectorMemoryIndexError, match="dimension"):
        index.upsert(entry)
    with pytest.raises(VectorMemoryIndexError, match="dimension"):
        index.search((1.0,), limit=1)


def test_qdrant_index_normalizes_invalid_provider_response() -> None:
    """Malformed provider response は VectorMemoryIndexError へ正規化する。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"result": {}})
        return httpx.Response(200, content=b"not-json")

    client = httpx.Client(base_url="http://qdrant.test", transport=httpx.MockTransport(handler))
    index = QdrantVectorMemoryIndex(
        url="http://unused.test", collection="memory", dimension=2, client=client
    )

    with pytest.raises(VectorMemoryIndexError, match="invalid response"):
        index.search((1.0, 0.0), limit=1)


def test_qdrant_existing_collection_matching_dimension_succeeds() -> None:
    """既存 collection の vector size が一致すれば初期化できる。"""
    client = httpx.Client(
        base_url="http://qdrant.test",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json=_collection_info(2))
        ),
    )

    index = QdrantVectorMemoryIndex(
        url="http://unused.test", collection="memory", dimension=2, client=client
    )

    assert index.ids() == ()


def test_qdrant_existing_collection_dimension_mismatch_fails() -> None:
    """既存 collection の vector size 不一致は index incompatibility とする。"""
    client = httpx.Client(
        base_url="http://qdrant.test",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json=_collection_info(3))
        ),
    )

    with pytest.raises(VectorMemoryIndexError, match="dimension mismatch"):
        QdrantVectorMemoryIndex(
            url="http://unused.test", collection="memory", dimension=2, client=client
        )


def test_qdrant_missing_collection_is_created_with_configured_dimension() -> None:
    """未作成 collection は指定 dimension/Cosine で作成する。"""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(404)
        return httpx.Response(200, json={"result": True})

    client = httpx.Client(base_url="http://qdrant.test", transport=httpx.MockTransport(handler))

    QdrantVectorMemoryIndex(
        url="http://unused.test", collection="memory", dimension=7, client=client
    )

    assert [request.method for request in requests] == ["GET", "PUT"]
    assert json.loads(requests[1].content) == {"vectors": {"size": 7, "distance": "Cosine"}}


def test_qdrant_metadata_round_trip_preserves_embedding_provider() -> None:
    """Point payload から provider/model/dimension metadata を復元する。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/collections/memory":
            return httpx.Response(200, json=_collection_info(2))
        return httpx.Response(
            200,
            json={
                "result": {
                    "payload": {
                        "memory_id": "m1",
                        "source_digest": "digest",
                        "embedding_provider": "fake",
                        "embedding_model": "fake-v1",
                        "embedding_dimension": 2,
                        "metadata": {"topic": "tea"},
                    },
                    "vector": [1.0, 0.0],
                }
            },
        )

    client = httpx.Client(base_url="http://qdrant.test", transport=httpx.MockTransport(handler))
    index = QdrantVectorMemoryIndex(
        url="http://unused.test", collection="memory", dimension=2, client=client
    )

    metadata = index.metadata(MemoryId("m1"))
    entry = index.entry(MemoryId("m1"))

    assert metadata is not None
    assert entry is not None
    assert entry.vector == (1.0, 0.0)
    assert entry.metadata == {"topic": "tea"}
    assert metadata.embedding_provider == "fake"
    assert metadata.embedding_model == "fake-v1"
    assert metadata.embedding_dimension == 2


def test_rebuilder_detects_provider_mismatch_from_qdrant_metadata() -> None:
    """Qdrant payload の provider mismatch は incompatible として再構築する。"""
    record = MemoryRecord(id=MemoryId("m1"), text="green tea")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/collections/memory":
            return httpx.Response(200, json=_collection_info(2))
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "result": {
                        "payload": {
                            "memory_id": "m1",
                            "source_digest": memory_record_digest(record),
                            "embedding_provider": "other",
                            "embedding_model": "fake-v1",
                            "embedding_dimension": 2,
                        }
                    }
                },
            )
        return httpx.Response(200, json={"result": {"status": "ok"}})

    client = httpx.Client(base_url="http://qdrant.test", transport=httpx.MockTransport(handler))
    index = QdrantVectorMemoryIndex(
        url="http://unused.test", collection="memory", dimension=2, client=client
    )
    store = InMemoryMemoryStore(records=(record,))

    stats = MemoryVectorIndexRebuilder(
        store=store,
        index=index,
        embedding=DeterministicFakeEmbedding(dimension=2),
    ).rebuild()

    assert stats.incompatible == 1
    assert stats.upserted == 1
    assert any(request.method == "PUT" for request in requests)
