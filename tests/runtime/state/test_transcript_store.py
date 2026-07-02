"""NullTranscriptStore tests。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.contracts.transcript import TranscriptQuery
from iris.runtime.state.transcript import NullTranscriptStore
from tests.helpers.transcript import make_transcript_record

pytestmark = pytest.mark.anyio


async def test_null_transcript_store_drops_records_and_prune_is_noop() -> None:
    """保存無効時は append / query / prune が副作用を持たない。"""
    store = NullTranscriptStore()

    await store.append((make_transcript_record("tr-null", "ignored"),))
    records = await store.query(TranscriptQuery())
    result = await store.prune_expired(datetime(2026, 7, 1, tzinfo=UTC))

    assert records == ()
    assert result.deleted_count == 0
