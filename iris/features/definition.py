"""フィーチャー定義プロトコルとコンテナ。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from iris.cognitive.cycle.models import PipelineStepResult
    from iris.cognitive.cycle.pipeline import PipelineStep
    from iris.contracts.availability import AvailabilitySnapshot
    from iris.contracts.event_reaction import (
        EventReactionDecision,
        EventReactionGenerationResult,
        EventReactionPrompt,
    )
    from iris.contracts.learning import LearningEvent, RuntimeLearningEvent
    from iris.contracts.observations import ActivityEventObservation, Observation
    from iris.contracts.presentation import ActionPlanPresenter
    from iris.contracts.workspace_context import SituationContextSnapshot


class ObservationSource(Protocol):
    """外部観測ソースのプロトコル。"""

    async def poll(self) -> Observation | None:
        """次の観測をポーリングする。利用可能なものがない場合はNone。"""


class LearningHook(Protocol):
    """アクション後学習フックのプロトコル。"""

    async def after_action_result(self, event: LearningEvent) -> None:
        """実行されたアクションの結果を処理する。"""


class RuntimeLearningHook(Protocol):
    """runtime outcome後学習フックのプロトコル。"""

    async def after_runtime_event(self, event: RuntimeLearningEvent) -> None:
        """配送結果を伴わないruntime learning eventを処理する。"""


class BackgroundLoopTask(Protocol):
    """独自周期で1 iterationずつ動く feature-owned loop task。"""

    name: str

    async def run_once(self) -> None:
        """バックグラウンドジョブの1イテレーションを実行する。"""


class ActivityReactionPlanner(Protocol):
    """アクティビティに対するリアクションを計画するプロトコル。"""

    def plan(
        self,
        observation: ActivityEventObservation,
        *,
        availability: AvailabilitySnapshot | None,
    ) -> EventReactionDecision:
        """リアクションを計画する。"""
        ...


@runtime_checkable
class ActivityReactionPromptProvider(Protocol):
    """反応plannerに対応するbounded prompt入力の提供protocol。"""

    def build_prompt(
        self,
        observation: ActivityEventObservation,
        *,
        situation_context: SituationContextSnapshot,
    ) -> EventReactionPrompt | None:
        """観測と状況からprompt入力を作る。"""
        ...


class EventReactionGenerator(Protocol):
    """runtimeへ注入するイベント反応生成port。"""

    async def generate(
        self,
        prompt: EventReactionPrompt,
    ) -> EventReactionGenerationResult:
        """Bounded promptから反応候補を生成する。"""
        ...


class FeatureKind(StrEnum):
    """Runtime feature の運用上の種別。"""

    COMPANION = "companion"
    DIAGNOSTIC = "diagnostic"


@dataclass(frozen=True)
class FeatureDefinition:
    """パイプラインステップ、観測ソース、フックを持つ垂直フィーチャースライス。"""

    name: str
    kind: FeatureKind = FeatureKind.COMPANION
    cognitive_steps: tuple[PipelineStep[PipelineStepResult], ...] = ()
    activity_reaction_planners: tuple[ActivityReactionPlanner, ...] = ()
    observation_sources: tuple[ObservationSource, ...] = ()
    learning_hooks: tuple[LearningHook, ...] = ()
    runtime_learning_hooks: tuple[RuntimeLearningHook, ...] = ()
    background_loop_tasks: tuple[BackgroundLoopTask, ...] = ()
    action_plan_presenters: tuple[ActionPlanPresenter, ...] = ()
