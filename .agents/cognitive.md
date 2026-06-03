# Cognitive Cycle Implementation Rules

You are implementing Iris's cognitive architecture. The core design prevents spaghetti code and ensures testability.

## CognitiveCycle: Pipeline Coordinator (NOT God Service)

```python
class CognitiveCycle:
    async def run(self, observation: Observation) -> CycleResult:
        ...
```

`CognitiveCycle.run()` is ONLY a pipeline coordinator. It orchestrates steps in order.
It MUST NOT contain: LLM prompt construction, memory updates, relationship updates, adapter calls, safety checks.

### Standard Pipeline Order

```
Observation
→ PerceptionStep
→ MemoryRetrievalStep
→ AppraisalStep
→ MotivationStep
→ PlanningStep
→ ActionSelectionStep
→ ActionPlan
```

## PipelineStep Contract (HARD RULES)

### RULE 1: Steps must NOT call each other

```python
# FORBIDDEN
memory → affect (direct call)
affect → policy (direct call)
policy → action (direct call)

# REQUIRED
CognitiveCycle → memory step
CognitiveCycle → affect step
CognitiveCycle → motivation step
CognitiveCycle → policy step
CognitiveCycle → action step
```

### RULE 2: Steps must NOT mutate WorkspaceFrame

Each step:
1. Receives `WorkspaceFrame` (read-only)
2. Returns a typed `PipelineStepResult`
3. `FrameBuilder` integrates results into a NEW `WorkspaceFrame`

```python
# REQUIRED pattern
for step in self._steps:
    result = await step.run(frame)
    frame = self._frame_builder.apply(frame, result)

# FORBIDDEN pattern
memory = await self.memory.search(user_text)
mood = self.relationship.update(memory)
reply = await self.llm.chat(memory, mood, user_text)
await self.discord.send(reply)
```

### RULE 3: Step results must be typed

Every step returns a `PipelineStepResult` subclass. Never return untyped `dict` or `Any`.

## WorkspaceFrame Rules

`WorkspaceFrame` is a frozen dataclass holding one-turn typed snapshot.

### ALLOWED contents
- `observation`
- `interpreted_input`
- `identity_context`
- `conversation_context`
- `retrieved_memory_summary`
- `affect_state`
- `relationship_snapshot`
- `motivation_state`
- `goals`
- `constraints`
- `candidate_actions`

### FORBIDDEN contents
- Store objects (don't put DB/store references in workspace)
- Adapter references
- Manager/service references
- Full past logs
- `dict[str, Any]` or `dict[str, object]`
- Raw LLM prompt strings

### Frame mutation pattern

```python
# REQUIRED
return replace(frame, memory_summary=MemorySummary(retrieved_memories=memories))

# FORBIDDEN
frame.state["facts"] = facts
frame.managers["memory"] = memory_manager
```

## Learning Hooks (Post-ActionResult)

Learning happens AFTER `ActionResult` is received. This is mandatory because you need to know:
- Did the message send successfully?
- Was it blocked by safety?
- Was it cancelled by user interrupt?

### Hot path (LearningHook) — execute synchronously
- Append conversation log
- Update working memory
- Light relationship updates
- Enqueue background jobs

### Background path (BackgroundJob) — execute async, outside hot path
- Long-term memory extraction
- LangMem extraction
- Persona patch proposal
- Episodic → semantic promotion
- Heavy reflection

## Proactive Behavior

Proactive speech is NOT a separate system. It's a `CognitiveCycle` triggered by an internal `Observation`:

```
Scheduler → IdleTickObservation → CognitiveCycle → ... → SpeakAction or NoAction
```

`features/proactive_talk/` must NOT modify internal implementations of `cognitive/memory/` or `cognitive/policy/`.

## Response Generation (LLM-backed text)

Response generation lives in `cognitive/action/response.py` as a `PipelineStep`:
1. Takes `WorkspaceFrame`
2. Builds typed response prompt (using frame fields)
3. Calls injected response generator (via port)
4. Returns `ActionSelectionResult` (does not mutate frame directly)
5. `FrameBuilder` integrates it into `WorkspaceFrame`

The step does NOT know about LLM provider shapes. `runtime/wiring/` handles that.

## Feature Extension Points

Features register via `FeatureDefinition`:

```python
@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    pipeline_steps: Sequence[PipelineStep[PipelineStepResult]] = ()
    observation_sources: Sequence[ObservationSource] = ()
    learning_hooks: Sequence[LearningHook] = ()
    background_jobs: Sequence[BackgroundJob] = ()
```

### Feature rules
- Each feature: `features/<name>/feature.py` returns `FeatureDefinition`
- `runtime/wiring/features.py` only collects and registers `FeatureDefinition`s
- Features MUST NOT import from `adapters/`, `runtime/`, `presentation/`, `safety/`
- Features MUST NOT mutate `WorkspaceFrame` directly
- Features MUST NOT use global registries

```python
# REQUIRED
def define_feature() -> FeatureDefinition:
    return FeatureDefinition(
        name="chat",
        pipeline_steps=(ChatActionSelectionStep(llm_port),),
        learning_hooks=(ConversationLogHook(store),),
    )

# FORBIDDEN
from iris.cognitive.cycle.service import global_cycle
global_cycle.register_hook(...)
```

## Presentation Layer

`presentation/` decides HOW to show the output. `cognitive/` decides WHAT to do. `adapters/` decides WHERE to send it.

```python
# MVP
ActionPlan → SimplePresenter → PresentedOutput

# Future
ActionPlan → PerformanceDirector → Text + Voice + Expression + Timing
```
