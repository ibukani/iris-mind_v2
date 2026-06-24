# Architecture Rules

Iris is organized around strict dependency direction. Do not trade these boundaries for short-term convenience.

## Layer dependency direction

Allowed direction:

```text
contracts → core
cognitive → contracts, core
presentation → contracts, core
features → contracts, cognitive extension protocols, core
adapters → contracts, core
safety → contracts, core
runtime → cognitive, features, adapters, presentation, safety, contracts, core
```

Only `runtime/` may compose all layers.

## Forbidden imports

| Source layer | Must not import |
|---|---|
| `iris/cognitive/**` | `iris/adapters/**`, `iris/runtime/**`, `iris/features/**` |
| `iris/contracts/**` | `iris/cognitive/**`, `iris/adapters/**`, `iris/runtime/**` |
| `iris/features/**` | `iris/adapters/**`, `iris/runtime/**`, `iris/presentation/**`, `iris/safety/**` |
| `iris/adapters/**` | `iris/cognitive/**` |

## Layer responsibilities

### `iris/core/`

Allowed:

- IDs
- time helpers
- result/error primitives
- low-level type utilities

Forbidden:

- LLM logic
- memory logic
- conversation logic
- feature utilities
- adapter code

### `iris/contracts/`

Allowed:

- typed cross-layer contracts
- `Observation`
- `ActionPlan`
- `PresentedOutput`
- `AppAction`
- `ActionResult`
- memory, identity, affect, policy contracts

Forbidden:

- provider clients
- cognitive implementations
- runtime wiring
- broad `ports.py` dumping grounds

Ports belong near the consuming module.

### `iris/cognitive/`

Allowed:

- cognitive cycle orchestration
- pipeline steps
- workspace frame construction
- perception, memory retrieval, affect, relationship, policy, action selection

Forbidden:

- provider API calls
- presentation formatting
- app-specific command execution
- safety gate execution
- feature registration

### `iris/presentation/`

Allowed:

- converting `ActionPlan` to `PresentedOutput`
- converting feature candidates such as `ReactionCandidate` to `PresentedOutput`
- style, emotion, expression, timing, priority, and interruptibility hints

Forbidden:

- deciding whether a feature should react
- running safety gates
- importing runtime/features/adapters/safety
- executing app actions

### `iris/features/`

Allowed:

- vertical feature slices
- `FeatureDefinition` providers
- feature-specific policy, planning, scoring, candidate generation, templates
- feature-specific pipeline steps, learning hooks, background jobs, observation sources

Forbidden:

- importing adapters/runtime/presentation/safety
- mutating cognitive internals
- global registration side effects

### `iris/adapters/`

Allowed:

- OpenAI or other LLM provider translation
- memory backend implementations
- external app gateway boundaries
- transport adapters
- SDK wrappers
- backend implementations for runtime-owned ports, when architecture guards grant a narrow exception
- external SDK usage

Adapter to runtime exceptions must stay narrow. A backend adapter may implement a runtime-owned port only when:

- the port is intentionally owned by the consuming runtime module
- the adapter imports only that narrow port module
- the adapter does not import runtime wiring, service, app, ingress, scheduler, delivery, lifecycle, or observability
- the file/import pair is listed in architecture tests with a reason

Forbidden:

- cognitive decisions
- relationship updates
- presentation decisions
- safety decisions

### `iris/runtime/`

Allowed:

- startup
- config
- dependency wiring
- lifecycle
- scheduler
- delivery
- ingress orchestration
- observability
- process-local runtime state
- selecting adapter implementations

Forbidden:

- domain model definitions
- cognitive business logic
- feature-specific policy, planning, scoring, candidate generation, or templates
- presentation formatting
- hidden service locator behavior

## Required architectural shape

The core turn path remains:

```text
Observation
→ CognitiveCycle.run()
→ typed PipelineStep results
→ FrameBuilder
→ WorkspaceFrame
→ ActionPlan
→ ActionSafetyGate
→ Presenter
→ PresentedOutput
→ OutputSafetyGate
→ AppAction
→ ActionResult
```

Do not bypass this path for convenience.
