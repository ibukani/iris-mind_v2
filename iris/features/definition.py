"""フィーチャー定義プロトコルとコンテナ。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.cognitive.cycle.models import PipelineStepResult
    from iris.cognitive.cycle.pipeline import PipelineStep
    from iris.contracts.actions import ActionResult
    from iris.contracts.observations import Observation


class ObservationSource(Protocol):
    """外部観測ソースのプロトコル。"""

    async def poll(self) -> Observation | None:
        """次の観測をポーリングする。利用可能なものがない場合はNone。"""


class LearningHook(Protocol):
    """アクション後学習フックのプロトコル。"""

    async def after_action_result(self, result: ActionResult) -> None:
        """実行されたアクションの結果を処理する。"""


class BackgroundJob(Protocol):
    """バックグラウンドジョブのプロトコル。"""

    name: str

    async def run_once(self) -> None:
        """バックグラウンドジョブの1イテレーションを実行する。"""


@dataclass(frozen=True)
class FeatureDefinition:
    """パイプラインステップ、観測ソース、フックを持つ垂直フィーチャースライス。"""

    name: str
    pipeline_steps: Sequence[PipelineStep[PipelineStepResult]] = ()
    observation_sources: Sequence[ObservationSource] = ()
    learning_hooks: Sequence[LearningHook] = ()
    background_jobs: Sequence[BackgroundJob] = ()
