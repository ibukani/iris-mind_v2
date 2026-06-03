# Architecture Rules for AI Coding Agents

You are implementing Iris, a cognitive runtime for an AI companion / Neuro-sama style agent.
Follow these rules strictly. Breaking them creates technical debt.

## Layer Dependency Rules

```
contracts → core
cognitive → contracts, core
presentation → contracts, core
features → contracts, cognitive extension protocols, core
adapters → contracts, core
safety → contracts, core
runtime → cognitive, features, adapters, presentation, safety, contracts, core
```

### FORBIDDEN IMPORTS

Do NOT write any of these imports:

| Layer | Must NOT import |
|-------|----------------|
| `cognitive/` | `adapters/`, `runtime/`, `features/` |
| `contracts/` | `cognitive/`, `adapters/`, `runtime/` |
| `features/` | `adapters/` (unless explicitly registered via FeatureDefinition) |
| `adapters/` | `cognitive/` |

Only `runtime/` is allowed to know about all layers.

## Directory Structure (Where to Put Code)

```
iris/
├── core/           # IDs, Time, Result type, Errors, Type utils ONLY
├── contracts/      # Shared types: Observation, Action, Message, Memory, Affect
├── runtime/        # App startup, config, wiring, scheduler, background jobs
│   └── wiring/     # Constructor injection only. NO business logic.
├── cognitive/      # Core engine: perception, memory, affect, motivation, policy, action, learning
│   ├── cycle/      # CognitiveCycle (pipeline coordinator), steps, FrameBuilder
│   └── workspace/  # WorkspaceFrame definition
├── presentation/   # Convert ActionPlan → PresentedOutput
├── features/       # Vertical feature slices (chat, proactive_talk, memory_consolidation, etc.)
├── adapters/       # External tech boundaries (LLM, stores, AppGateway, embeddings)
└── safety/         # ActionSafetyGate, OutputSafetyGate
```

### What Goes Where (Quick Reference)

| If you are writing... | Put it in... |
|----------------------|-------------|
| Common ID, Result type, errors | `core/` |
| Shared type definitions | `contracts/` |
| App startup, dependency wiring | `runtime/wiring/` |
| Cognitive processing logic | `cognitive/` |
| How output looks (text, style) | `presentation/` |
| New feature (chat, proactive) | `features/<name>/` |
| LLM/DB/Discord connection code | `adapters/` |
| Dangerous output filtering | `safety/` |

### `core/` Restrictions

ALLOW: IDs, time helpers, Result type, errors, type utilities.

FORBID: Memory logic, conversation logic, LLM logic, adapter logic, feature common code.

### `contracts/` Restrictions

ALWAYS put ports (interfaces/abstract base classes) in the consuming module, NOT in `contracts/ports.py`.

Correct port placement:
```
cognitive/action/ports.py
cognitive/memory/ports.py
presentation/ports.py
safety/ports.py
adapters/app_gateway/ports.py
```

### `runtime/wiring/` Restrictions

- Constructor injection ONLY
- Do NOT call `resolve()`, `get_service()`, `locate()`, or any service locator
- Do NOT define domain classes here (CognitiveCycle, PipelineStep, etc.)
- Do NOT write business logic or cognitive logic here

## Key Type Responsibilities

### Observation
Input that enters Iris. Always convert external app events to Observation BEFORE they reach cognitive code.

Types: `UserMessageObservation`, `TranscriptObservation`, `IdleTickObservation`, `AudienceMessageObservation`, `GameEventObservation`

### WorkspaceFrame
Typed snapshot shared across one turn. Frozen dataclass. NO `dict[str, Any]`.

### ActionPlan
What Iris wants to do (app-agnostic). NOT the final external action.

### PresentedOutput
How ActionPlan should look (text, style, emotion_hint, expression_hint, timing).

### AppAction
Concrete command for external apps: `SendMessageAction`, `SpeakAction`, `ToolCallAction`.

### ActionResult
Result of executing AppAction: status, error_reason, external_message_id.

## Runtime Flow (Must Follow)

```
Observation
→ CognitiveCycle.run()
  → PipelineStep results
  → FrameBuilder → WorkspaceFrame
→ ActionPlan
→ ActionSafetyGate
→ Presenter
→ PresentedOutput
→ OutputSafetyGate
→ AppAction
→ ActionResult
→ LearningHook
→ BackgroundJob
```

## no-action Semantics

The canonical no-action representation:
```python
ActionPlan(turn_intent="no_action", candidate_text=None, should_respond=False)
```

Rules for no-action:
- Do NOT call LLM
- Do NOT generate user-visible text
- Do NOT send to external apps
- Do NOT behave as proactive speech
- `IrisApp.process_observation()` must skip safety gate, presenter, output gate and return `PresentedOutput(text=None)`
