"""QdrantVectorMemoryIndex の network-free adapter test。"""

from __future__ import annotations

import json

import httpx
import pytest

from iris.adapters.memory.qdrant import QdrantVectorMemoryIndex
from iris.contracts.memory import (
    MemoryId,
    MemoryKind,
    VectorMemoryEntry,
    VectorMemoryIndexError,
    VectorMemorySearchFilter,
)
from iris.core.ids import ActorId, ObservationId, SpaceId


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
