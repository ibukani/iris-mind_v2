# Minimal Interface Specification

この章は、AIコーディングエージェントに最初に実装させる最小インターフェース仕様である。
実装開始時は、この章の型を優先し、ファイルごとに独自型を増やさない。

---

## `core/ids.py`

```python
from typing import NewType

ObservationId = NewType("ObservationId", str)
ActionId = NewType("ActionId", str)
TurnId = NewType("TurnId", str)
SessionId = NewType("SessionId", str)
ConversationId = NewType("ConversationId", str)
UserId = NewType("UserId", str)
CorrelationId = NewType("CorrelationId", str)
ExternalRef = NewType("ExternalRef", str)
```

ID はただの `str` と混同しない。
外部アプリの ID は `ExternalRef` として扱い、Iris 内部 ID と直接混ぜない。

---

## `contracts/identity.py`

```python
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from iris.core.ids import UserId, ExternalRef

@dataclass(frozen=True)
class Identity:
    user_id: UserId
    display_name: str
    provider: str
    provider_subject: ExternalRef
    metadata: Mapping[str, str] = MappingProxyType({})
```

`metadata` は外部由来の補助情報に限定する。
認知判断に使う状態を `metadata` に押し込まない。

---

## `contracts/observations.py`

```python
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from iris.contracts.identity import Identity
from iris.core.ids import ObservationId, SessionId, ExternalRef

class ObservationKind(StrEnum):
    USER_MESSAGE = "user_message"
    TRANSCRIPT = "transcript"
    IDLE_TICK = "idle_tick"
    AUDIENCE_MESSAGE = "audience_message"
    GAME_EVENT = "game_event"

@dataclass(frozen=True)
class Observation:
    observation_id: ObservationId
    session_id: SessionId
    actor: Identity | None
    occurred_at: datetime
    kind: ObservationKind

@dataclass(frozen=True)
class UserMessageObservation(Observation):
    text: str
    external_message_id: ExternalRef | None = None

@dataclass(frozen=True)
class IdleTickObservation(Observation):
    reason: str
```

外部アプリ固有のイベント名を `cognitive/` に入れない。
Discord、Twitch、Voice などのイベントは AppGateway 側で `Observation` に変換する。

---

## `contracts/actions.py`

```python
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from iris.core.ids import ActionId, CorrelationId, SessionId, ExternalRef

class ActionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"

@dataclass(frozen=True)
class ActionPlan:
    turn_intent: str
    candidate_text: str | None
    should_respond: bool
    priority: int
    interruptible: bool = True

@dataclass(frozen=True)
class PresentedOutput:
    text: str | None
    style_hint: str | None = None
    emotion_hint: str | None = None
    expression_hint: str | None = None
    delay_ms: int = 0
    priority: int = 0
    interruptible: bool = True

@dataclass(frozen=True)
class AppAction:
    action_id: ActionId
    session_id: SessionId
    correlation_id: CorrelationId

@dataclass(frozen=True)
class SendMessageAction(AppAction):
    text: str

@dataclass(frozen=True)
class NoAction(AppAction):
    reason: str

@dataclass(frozen=True)
class ActionResult:
    action_id: ActionId
    correlation_id: CorrelationId
    status: ActionStatus
    delivered_at: datetime | None = None
    external_message_id: ExternalRef | None = None
    error_reason: str | None = None
```

`ActionPlan` は「何をしたいか」、`PresentedOutput` は「どう見せるか」、`AppAction` は「外部アプリが実行する命令」である。
この3つを混ぜない。

---

## `cognitive/workspace/frame.py`

```python
from dataclasses import dataclass, field

from iris.contracts.observations import Observation
from iris.contracts.actions import ActionPlan

@dataclass(frozen=True)
class InterpretedInput:
    text: str | None
    language: str | None
    intent_hint: str | None = None

@dataclass(frozen=True)
class MemorySummary:
    retrieved_memories: tuple[MemorySearchResult, ...] = ()

@dataclass(frozen=True)
class AffectSnapshot:
    mood_label: str | None = None
    arousal: float = 0.0
    valence: float = 0.0

@dataclass(frozen=True)
class RelationshipSnapshot:
    user_label: str | None = None
    affinity: float = 0.0
    trust: float = 0.0
    familiarity: float = 0.0

@dataclass(frozen=True)
class GoalCandidate:
    name: str
    reason: str
    priority: int

@dataclass(frozen=True)
class PolicyConstraint:
    name: str
    reason: str
    blocks_response: bool = False

@dataclass(frozen=True)
class WorkspaceFrame:
    observation: Observation
    interpreted_input: InterpretedInput | None = None
    memory_summary: MemorySummary = field(default_factory=MemorySummary)
    affect: AffectSnapshot = field(default_factory=AffectSnapshot)
    relationship: RelationshipSnapshot = field(default_factory=RelationshipSnapshot)
    goals: tuple[GoalCandidate, ...] = ()
    constraints: tuple[PolicyConstraint, ...] = ()
    candidate_action_plans: tuple[ActionPlan, ...] = ()
```

`WorkspaceFrame` は frozen dataclass とする。
更新したい場合は `FrameBuilder` が新しい frame を返す。

禁止例。

```python
frame.context["memory"] = memory_store
frame.extra["relationship_manager"] = manager
frame.prompt = huge_prompt_text
```

---

## `cognitive/cycle/models.py`

```python
from dataclasses import dataclass
from enum import StrEnum

from iris.contracts.actions import ActionPlan
from iris.cognitive.workspace.frame import WorkspaceFrame

class StepStatus(StrEnum):
    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"

@dataclass(frozen=True)
class PipelineStepResult:
    step_name: str
    status: StepStatus
    reason: str | None = None

@dataclass(frozen=True)
class PerceptionResult(PipelineStepResult):
    text: str | None = None
    language: str | None = None
    intent_hint: str | None = None

@dataclass(frozen=True)
class MemoryRetrievalResult(PipelineStepResult):
    memories: tuple[MemorySearchResult, ...] = ()

@dataclass(frozen=True)
class AppraisalResult(PipelineStepResult):
    mood_label: str | None = None
    arousal: float = 0.0
    valence: float = 0.0

@dataclass(frozen=True)
class RelationshipResult(PipelineStepResult):
    user_label: str | None = None
    affinity: float = 0.0
    trust: float = 0.0
    familiarity: float = 0.0

@dataclass(frozen=True)
class MotivationResult(PipelineStepResult):
    goals: tuple[str, ...] = ()

@dataclass(frozen=True)
class PolicyResult(PipelineStepResult):
    constraints: tuple[str, ...] = ()
    response_allowed: bool = True

@dataclass(frozen=True)
class ActionSelectionResult(PipelineStepResult):
    action_plans: tuple[ActionPlan, ...] = ()

@dataclass(frozen=True)
class CycleResult:
    frame: WorkspaceFrame
    selected_plan: ActionPlan
```

各 result は必要になった時点で分割してよい。
ただし、`dict` で代用しない。

---

## `cognitive/cycle/pipeline.py`

```python
from typing import Protocol, TypeVar, Generic

from iris.cognitive.cycle.models import PipelineStepResult
from iris.cognitive.workspace.frame import WorkspaceFrame

ResultT = TypeVar("ResultT", bound=PipelineStepResult)

class PipelineStep(Protocol, Generic[ResultT]):
    name: str

    async def run(self, frame: WorkspaceFrame) -> ResultT:
        ...
```

Step は store、adapter、manager を直接持ってもよいが、それは constructor injection で受け取る。
グローバル registry から取り出してはいけない。

---

## `cognitive/cycle/frame_builder.py`

```python
from dataclasses import replace

from iris.cognitive.cycle.models import (
    PipelineStepResult,
    PerceptionResult,
    MemoryRetrievalResult,
    AppraisalResult,
    RelationshipResult,
    MotivationResult,
    PolicyResult,
    ActionSelectionResult,
)
from iris.cognitive.workspace.frame import (
    WorkspaceFrame,
    InterpretedInput,
    MemorySummary,
    AffectSnapshot,
    RelationshipSnapshot,
    GoalCandidate,
    PolicyConstraint,
)

class FrameBuilder:
    def apply(self, frame: WorkspaceFrame, result: PipelineStepResult) -> WorkspaceFrame:
        match result:
            case PerceptionResult():
                return replace(
                    frame,
                    interpreted_input=InterpretedInput(
                        text=result.text,
                        language=result.language,
                        intent_hint=result.intent_hint,
                    ),
                )
            case MemoryRetrievalResult():
                return replace(
                    frame,
                    memory_summary=MemorySummary(retrieved_memories=result.memories),
                )
            case AppraisalResult():
                return replace(
                    frame,
                    affect=AffectSnapshot(
                        mood_label=result.mood_label,
                        arousal=result.arousal,
                        valence=result.valence,
                    ),
                )
            case RelationshipResult():
                return replace(
                    frame,
                    relationship=RelationshipSnapshot(
                        user_label=result.user_label,
                        affinity=result.affinity,
                        trust=result.trust,
                        familiarity=result.familiarity,
                    ),
                )
            case MotivationResult():
                return replace(
                    frame,
                    goals=tuple(
                        GoalCandidate(name=goal, reason="pipeline", priority=index)
                        for index, goal in enumerate(result.goals)
                    ),
                )
            case PolicyResult():
                return replace(
                    frame,
                    constraints=tuple(
                        PolicyConstraint(name=item, reason="pipeline")
                        for item in result.constraints
                    ),
                )
            case ActionSelectionResult():
                return replace(frame, candidate_action_plans=result.action_plans)
            case _:
                raise TypeError(f"Unsupported step result: {type(result).__name__}")
```

`FrameBuilder` にも業務ロジックを書かない。
役割は result を frame に写すことだけである。

---

## `cognitive/cycle/service.py`

```python
from collections.abc import Sequence

from iris.contracts.actions import ActionPlan
from iris.contracts.observations import Observation
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import CycleResult, PipelineStepResult
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.workspace.frame import WorkspaceFrame

class CognitiveCycle:
    def __init__(
        self,
        steps: Sequence[PipelineStep[PipelineStepResult]],
        frame_builder: FrameBuilder,
        fallback_plan: ActionPlan,
    ) -> None:
        self._steps = tuple(steps)
        self._frame_builder = frame_builder
        self._fallback_plan = fallback_plan

    async def run(self, observation: Observation) -> CycleResult:
        frame = WorkspaceFrame(observation=observation)

        for step in self._steps:
            result = await step.run(frame)
            frame = self._frame_builder.apply(frame, result)

        selected = self._select_action_plan(frame)
        return CycleResult(frame=frame, selected_plan=selected)

    def _select_action_plan(self, frame: WorkspaceFrame) -> ActionPlan:
        if frame.candidate_action_plans:
            return max(frame.candidate_action_plans, key=lambda plan: plan.priority)
        return self._fallback_plan
```

`CognitiveCycle` が許される処理は、順序制御、result 収集、frame 更新委譲、最終 plan 選択だけである。

禁止。

```python
prompt = build_prompt(frame)
text = await openai_client.chat(prompt)
memory_store.save(...)
relationship_manager.update(...)
discord_client.send(...)
```

---

## `features/definition.py`

MVP では、`FeatureDefinition` を小さく始める。

```python
from dataclasses import dataclass
from collections.abc import Sequence
from typing import Protocol

from iris.contracts.actions import ActionResult
from iris.contracts.observations import Observation
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.cycle.models import PipelineStepResult

class ObservationSource(Protocol):
    async def poll(self) -> Observation | None:
        ...

class LearningHook(Protocol):
    async def after_action_result(self, result: ActionResult) -> None:
        ...

class BackgroundJob(Protocol):
    name: str

    async def run_once(self) -> None:
        ...

@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    pipeline_steps: Sequence[PipelineStep[PipelineStepResult]] = ()
    observation_sources: Sequence[ObservationSource] = ()
    learning_hooks: Sequence[LearningHook] = ()
    background_jobs: Sequence[BackgroundJob] = ()
```

Phase 2 以降で必要になったら、以下を追加する。

```text
workspace_contributors
appraisal_providers
salience_scorers
goal_proposers
policy_constraints
action_providers
presenters
safety_gates
```

最初から空の extension point を大量に作らない。

---

## `presentation/presenter.py`

```python
from typing import Protocol

from iris.contracts.actions import ActionPlan, PresentedOutput

class Presenter(Protocol):
    async def present(self, plan: ActionPlan) -> PresentedOutput:
        ...

class SimplePresenter:
    async def present(self, plan: ActionPlan) -> PresentedOutput:
        return PresentedOutput(
            text=plan.candidate_text,
            priority=plan.priority,
            interruptible=plan.interruptible,
        )
```

`presentation/` は LLM provider や Discord API を知らない。

---

## `safety/action_gate.py` と `safety/output_filter.py`

```python
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from iris.contracts.actions import ActionPlan, PresentedOutput

class GateDecision(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"

@dataclass(frozen=True)
class SafetyDecision:
    decision: GateDecision
    reason: str | None = None

class ActionSafetyGate(Protocol):
    async def check_plan(self, plan: ActionPlan) -> SafetyDecision:
        ...

class OutputSafetyGate(Protocol):
    async def check_output(self, output: PresentedOutput) -> SafetyDecision:
        ...
```

MVP では常に allow する実装でよい。
ただし、呼び出し順序だけは最初から固定する。

---

## `adapters/app_gateway/ports.py`

```python
from typing import Protocol

from iris.contracts.actions import AppAction, ActionResult
from iris.contracts.observations import Observation

class AppGateway(Protocol):
    async def receive_observation(self) -> Observation | None:
        ...

    async def execute(self, action: AppAction) -> ActionResult:
        ...
```

AppGateway は cognitive 判断をしない。
外部世界と Iris 内部 contract の翻訳だけを担当する。

---

## 関連ドキュメント

- architecture.md: 各層の責務、ディレクトリ構成
- cognitive.md: 認知サイクルの設計思想
- mvp.md: MVP で作るもの / 作らないもの
