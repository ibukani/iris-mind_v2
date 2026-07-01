"""Memory write pipeline step and stable memory ID generation."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import TYPE_CHECKING, override

from iris.cognitive.cycle.models import MemoryWriteResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.memory.extraction import RuleBasedMemoryCandidateExtractor
from iris.cognitive.memory.policy import MemoryWritePolicy
from iris.contracts.memory import (
    MemoryId,
    MemoryRecord,
    VectorMemoryIndexError,
    vector_memory_entry_from_record,
)
from iris.core.metadata import immutable_metadata

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.cognitive.memory.candidates import MemoryCandidate, MemoryCandidateExtractor
    from iris.cognitive.workspace.frame import WorkspaceFrame
    from iris.contracts.embeddings import EmbeddingModel
    from iris.contracts.memory import MutableMemoryStore, VectorMemoryIndex
    from iris.contracts.metadata import ImmutableMetadata

_LOGGER = logging.getLogger(__name__)


def _generate_memory_id(candidate: MemoryCandidate) -> MemoryId:
    """候補の内容から安定したメモリ ID を生成する。

    同じ actor / space / kind / normalized_text の組み合わせからは
    常に同じ ID が生成されるため、重複保存を防ぐ。

    Args:
        candidate: 保存候補。

    Returns:
        MemoryId: 安定したハッシュベースのメモリ ID。
    """
    scope = f"{candidate.actor_id or ''}:{candidate.space_id or ''}:{candidate.kind.value}"
    normalized = candidate.text.strip().casefold()
    content = f"{scope}:{normalized}"
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]
    return MemoryId(f"memory:{digest}")


def _candidate_metadata(candidate: MemoryCandidate) -> ImmutableMetadata:
    """既存値を保ちつつ候補 provenance を正規化する。

    Returns:
        保存用の不変 metadata。
    """
    values = dict(candidate.metadata)
    values.setdefault("candidate_source", candidate.source.value)
    values.setdefault("retention_policy", candidate.retention_policy.value)
    values.setdefault("sensitivity", candidate.sensitivity.value)
    values.setdefault("review_required", "true" if candidate.review_required else "false")
    if candidate.reason is not None:
        values.setdefault("reason", candidate.reason)
    return immutable_metadata(values)


class MemoryWriteStep(PipelineStep[MemoryWriteResult]):
    """パイプラインステップ: フレームから候補を抽出して保存する。

    WorkspaceFrame から MemoryCandidate を抽出し、
    MutableMemoryStore に保存する。
    """

    name = "memory_write"

    def __init__(
        self,
        store: MutableMemoryStore,
        *,
        extractor: MemoryCandidateExtractor | None = None,
        policy: MemoryWritePolicy | None = None,
        vector_index: VectorMemoryIndex | None = None,
        embedding: EmbeddingModel | None = None,
        fail_open_on_index_error: bool = True,
    ) -> None:
        """保存先ストアと抽出器・ポリシーで初期化する。

        Args:
            store: メモリレコードの保存先。
            extractor: 候補抽出器。省略時は RuleBasedMemoryCandidateExtractor。
            policy: 保存ポリシー。省略時は MemoryWritePolicy。
            vector_index: ベクトル検索インデックス。指定時は write 成功後に upsert する。
            embedding: index entry を生成する埋め込みモデル。
            fail_open_on_index_error: index failure を正本 write 成功後に許容するか。

        Raises:
            ValueError: vector index と embedding の片方だけが指定された場合。
        """
        self._store = store
        self._extractor = extractor or RuleBasedMemoryCandidateExtractor()
        self._policy = policy or MemoryWritePolicy()
        self._vector_index = vector_index
        self._embedding = embedding
        self._fail_open_on_index_error = fail_open_on_index_error
        if (vector_index is None) != (embedding is None):
            msg = "vector_index and embedding must be configured together"
            raise ValueError(msg)

    @override
    async def run(self, frame: WorkspaceFrame) -> MemoryWriteResult:
        """フレームから候補を抽出・判定・保存する。

        Returns:
            MemoryWriteResult: 書き込み結果。
        """
        if frame.interpreted_input is None or not frame.interpreted_input.text:
            return MemoryWriteResult(
                step_name=self.name,
                status=StepStatus.SKIPPED,
                reason="no interpreted input text",
            )

        candidates: Sequence[MemoryCandidate] = self._extractor.extract(frame)
        written_ids: list[str] = []
        rejected_count = 0

        for candidate in candidates:
            if not self._policy.accept(candidate):
                rejected_count += 1
                continue

            memory_id = _generate_memory_id(candidate)
            record = MemoryRecord(
                id=memory_id,
                text=candidate.text,
                actor_id=candidate.actor_id,
                space_id=candidate.space_id,
                salience=candidate.salience,
                kind=candidate.kind,
                confidence=candidate.confidence,
                source_observation_id=candidate.source_observation_id,
                metadata=_candidate_metadata(candidate),
            )

            record = await asyncio.to_thread(self._store.update, record)
            await self._upsert_vector(record)
            written_ids.append(str(memory_id))

        status = StepStatus.OK if written_ids else StepStatus.SKIPPED
        return MemoryWriteResult(
            step_name=self.name,
            status=status,
            written_ids=tuple(written_ids),
            rejected_count=rejected_count,
        )

    async def _upsert_vector(self, record: MemoryRecord) -> None:
        """正本保存後に派生 index を更新する。

        Raises:
            VectorMemoryIndexError: fail-open 無効時に index 更新が失敗した場合。
        """
        if self._vector_index is None or self._embedding is None:
            return
        vector = await asyncio.to_thread(self._embedding.embed, record.text)
        entry = vector_memory_entry_from_record(
            record,
            vector=vector,
            embedding_provider=self._embedding.provider,
            embedding_model=self._embedding.model_id,
            embedding_dimension=self._embedding.dimension,
        )
        try:
            await asyncio.to_thread(self._vector_index.upsert, entry)
        except VectorMemoryIndexError:
            if not self._fail_open_on_index_error:
                raise
            _LOGGER.exception("memory vector index upsert failed", extra={"memory_id": record.id})
