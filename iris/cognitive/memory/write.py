"""Memory write pipeline step and stable memory ID generation."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, override

from iris.cognitive.cycle.models import MemoryWriteResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.memory.extraction import RuleBasedMemoryCandidateExtractor
from iris.cognitive.memory.policy import MemoryWritePolicy
from iris.contracts.memory import MemoryId, MemoryRecord
from iris.core.async_utils import run_sync_in_thread

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.cognitive.memory.candidates import MemoryCandidate, MemoryCandidateExtractor
    from iris.cognitive.workspace.frame import WorkspaceFrame
    from iris.contracts.memory import MutableMemoryStore, VectorMemoryIndex


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
    ) -> None:
        """保存先ストアと抽出器・ポリシーで初期化する。

        Args:
            store: メモリレコードの保存先。
            extractor: 候補抽出器。省略時は RuleBasedMemoryCandidateExtractor。
            policy: 保存ポリシー。省略時は MemoryWritePolicy。
            vector_index: ベクトル検索インデックス。指定時は write 成功後に upsert する。
        """
        self._store = store
        self._extractor = extractor or RuleBasedMemoryCandidateExtractor()
        self._policy = policy or MemoryWritePolicy()
        self._vector_index = vector_index

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
                metadata=candidate.metadata,
            )

            await run_sync_in_thread(self._store.update, record)
            if self._vector_index is not None:
                await run_sync_in_thread(
                    self._vector_index.upsert,
                    memory_id,
                    record.text,
                    dict(record.metadata),
                )
            written_ids.append(str(memory_id))

        status = StepStatus.OK if written_ids else StepStatus.SKIPPED
        return MemoryWriteResult(
            step_name=self.name,
            status=status,
            written_ids=tuple(written_ids),
            rejected_count=rejected_count,
        )
