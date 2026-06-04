# Copyright 2025 Iris Mind
"""Simple perception pipeline step."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.cognitive.cycle.models import PerceptionResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame


class SimplePerceptionStep(PipelineStep[PerceptionResult]):
    """Pipeline step that extracts text from the observation."""

    name = "perception"

    @override
    async def run(self, frame: WorkspaceFrame) -> PerceptionResult:
        """Extract text from the frame's observation and return a perception result.

        Returns:
            PerceptionResult: 観測から抽出されたテキストとメタデータ。
        """
        obs = frame.observation
        raw_text: object = getattr(obs, "text", None)
        text: str | None = raw_text if isinstance(raw_text, str) else str(obs.kind)
        return PerceptionResult(
            step_name=self.name,
            status=StepStatus.OK,
            text=text,
            language=None,
            intent_hint=None,
        )
