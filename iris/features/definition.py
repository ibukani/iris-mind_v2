from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from iris.cognitive.cycle.models import PipelineStepResult
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.contracts.actions import ActionResult
from iris.contracts.observations import Observation


class ObservationSource(Protocol):
    async def poll(self) -> Observation | None: ...


class LearningHook(Protocol):
    async def after_action_result(self, result: ActionResult) -> None: ...


class BackgroundJob(Protocol):
    name: str

    async def run_once(self) -> None: ...


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    pipeline_steps: Sequence[PipelineStep[PipelineStepResult]] = ()
    observation_sources: Sequence[ObservationSource] = ()
    learning_hooks: Sequence[LearningHook] = ()
    background_jobs: Sequence[BackgroundJob] = ()
