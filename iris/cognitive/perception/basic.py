# Copyright 2025 Iris Mind
"""シンプルな知覚パイプラインステップ。"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.cognitive.cycle.models import PerceptionResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.contracts.observations import ActorMessageObservation

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame


class SimplePerceptionStep(PipelineStep[PerceptionResult]):
    """観測からテキストを抽出するパイプラインステップ。"""

    name = "perception"

    @override
    async def run(self, frame: WorkspaceFrame) -> PerceptionResult:
        """フレームの観測からテキストを抽出し、知覚結果を返す。

        Returns:
            PerceptionResult: 観測から抽出されたテキストとメタデータ。
        """
        obs = frame.observation

        if isinstance(obs, ActorMessageObservation):
            text: str | None = obs.text
        else:
            text = str(obs.kind)
        return PerceptionResult(
            step_name=self.name,
            status=StepStatus.OK,
            text=text,
            language=None,
            intent_hint=None,
        )
