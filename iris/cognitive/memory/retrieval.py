# Copyright 2025 Iris Mind
"""メモリ検索パイプラインステップとレトリーバープロトコル。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, override

from iris.cognitive.cycle.models import MemoryRetrievalResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.contracts.memory import MemoryQuery, MemorySearchResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.cognitive.workspace.frame import WorkspaceFrame


class MemoryRetriever(Protocol):
    """メモリ検索バックエンドのプロトコル。"""

    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        """クエリに一致するメモリレコードを検索する。"""
        ...


class MemoryRetrievalStep(PipelineStep[MemoryRetrievalResult]):
    """現在のフレームに関連するメモリを取得するパイプラインステップ。"""

    name = "memory_retrieval"

    def __init__(self, retriever: MemoryRetriever, *, limit: int = 5) -> None:
        """Initialize with a retriever and result limit.

        Args:
            retriever: The memory retriever backend.
            limit: Maximum number of memory results to retrieve.
        """
        self._retriever = retriever
        self._limit = limit

    @override
    async def run(self, frame: WorkspaceFrame) -> MemoryRetrievalResult:
        """Retrieve memories relevant to the frame's interpreted input.

        Returns:
            MemoryRetrievalResult: 取得されたメモリ。入力がない場合は SKIPPED。
        """
        if frame.interpreted_input is None or frame.interpreted_input.text is None:
            return MemoryRetrievalResult(
                step_name=self.name,
                status=StepStatus.SKIPPED,
                reason="no interpreted input text",
                memories=(),
            )

        query = MemoryQuery(
            text=frame.interpreted_input.text,
            actor_id=(frame.actor_context.actor.actor_id if frame.actor_context.actor else None),
            space_id=frame.space_context.space_id,
            limit=self._limit,
        )
        memories = tuple(self._retriever.search(query))
        return MemoryRetrievalResult(
            step_name=self.name,
            status=StepStatus.OK,
            memories=memories,
        )
