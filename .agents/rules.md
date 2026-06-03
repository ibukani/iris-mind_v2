# Implementation Rules for AI Coding Agents

These are enforced rules. Violating any of them will be rejected in code review.

## Core Mandates (19 Rules)

1. Main processing is explicitly controlled by `CognitiveCycle`.
2. `CognitiveCycle` is a **pipeline coordinator**, not a God Service.
3. Each `PipelineStep` does NOT mutate `WorkspaceFrame` directly.
4. Each `PipelineStep` returns a **typed** result.
5. `FrameBuilder` integrates `StepResult` into `WorkspaceFrame`.
6. All external input MUST be converted to `Observation`.
7. All output MUST go through: `ActionPlan → ActionSafetyGate → Presentation → OutputSafetyGate → AppAction`.
8. Learning MUST happen after receiving `ActionResult`.
9. `cognitive/` MUST NOT import from `adapters/` or `runtime/`.
10. `cognitive/` MUST NOT import from `features/`.
11. Features MUST register via `FeatureDefinition` extension provider.
12. Features MUST NOT modify cognitive internals.
13. Service Locator / `resolve_optional` / global registry calls are **FORBIDDEN**.
14. New features go in `features/<name>/` as vertical slices.
15. Do NOT create compatibility shims, temporary wrappers, or legacy API adapters.
16. Do NOT add `action: str` dispatcher branches.
17. Do NOT use `dict[str, Any]` or `dict[str, object]` at internal boundaries.
18. `runtime/wiring` MUST use constructor injection only.
19. Dependency direction is enforced by architecture tests.

## v0.1 Extra Rules

These rules constrain v0.1 implementation. They do not change v1.2 direction; they prevent AI agents from making ambiguous choices.

1. `CognitiveCycle.run()` is **exclusively** a pipeline coordinator.
2. `CognitiveCycle.run()` must NOT contain: LLM prompt building, memory updates, relationship updates, adapter calls, safety checks.
3. `PipelineStep` receives `WorkspaceFrame`, returns typed `PipelineStepResult`.
4. `PipelineStep` does NOT mutate `WorkspaceFrame`.
5. Only `FrameBuilder` integrates step results into the next `WorkspaceFrame`.
6. MVP `FeatureDefinition` starts with minimal fields. Do not create empty stub implementations for unused extension points.
7. `dict[str, Any]`, `dict[str, object]`, `action: str` dispatchers, service locators are **FORBIDDEN** at internal boundaries.
8. Port legacy code by responsibility unit. Do NOT create compatibility wrappers for old structures.

## Wiring Rules (Mandatory)

- Use explicit **constructor injection** in all wiring files.
- Wiring files must NOT call `resolve()`, `get_service()`, `locate()`, or any service locator pattern.
- Wiring files must NOT define domain classes (`CognitiveCycle`, `PipelineStep`, etc.).
- `runtime/wiring/` is split by concern: `cognitive.py`, `adapters.py`, `features.py`, `presentation.py`, `safety.py`.

## Adding a Feature (Checklist)

When adding a new feature:
1. Create `features/<name>/feature.py`
2. Implement `def define_feature() -> FeatureDefinition:`
3. Register in `runtime/wiring/features.py` (just collect and register)
4. Feature must NOT import from `adapters/`, `runtime/`, `presentation/`, `safety/`
5. Feature must NOT mutate `WorkspaceFrame` directly
6. Feature uses only `FeatureDefinition` extension points

## Adapter Rules

### LLM Adapter (`adapters/llm/`)
- Accepts typed `LLMRequest`, returns typed `LLMResponse`
- Provider calls, model selection, auth, network I/O stay INSIDE the adapter boundary
- Tests and local MVP use deterministic `FakeLLMClient`
- OpenAI provider goes in `adapters/llm/openai.py` — API translation stays inside adapter
- Real provider config uses typed config injection (NOT global discovery)
- `cognitive/` does NOT import from `adapters/llm/`

### Memory Adapter (`adapters/memory/`)
- Accepts typed `MemoryQuery`, returns typed `MemorySearchResult`
- Tests and local MVP use deterministic `FakeMemoryStore`
- LangChain/LangMem/vector stores are optional backends behind `MemoryStore` interface
- `cognitive/` depends ONLY on `MemoryQuery` and `MemorySearchResult` types
- `cognitive/` does NOT import LangChain, LangMem, vector DB SDKs, or adapter types

### AppGateway (`adapters/app_gateway/`)
Responsibilities:
- Receive `Observation` from external apps
- Return `AppAction` to external apps
- Receive `ActionResult`
- Manage `correlation_id`/`turn_id`/`session_id`
- Map external refs to Iris internal refs

AppGateway must NOT:
- Make cognitive decisions
- Update memory
- Make proactive judgments
- Make presentation decisions
- Contain deep Discord/Voice-specific logic

## Anti-Pattern Checklist

Before committing, verify you have NOT introduced:

- [ ] `cognitive/` importing `adapters/` or `runtime/`
- [ ] `dict[str, Any]` or `dict[str, object]` at module boundaries
- [ ] `action: str` dispatcher with new branch
- [ ] Service locator / global registry pattern
- [ ] Compatibility wrapper for old code
- [ ] `WorkspaceFrame` mutation in any `PipelineStep`
- [ ] Direct step-to-step calls (e.g., `memory_step → affect_step`)
- [ ] `CognitiveCycle.run()` doing LLM work, memory work, or adapter calls
- [ ] Feature modifying cognitive internals directly
- [ ] Untyped step results
- [ ] Adapter leaking implementation types into cognitive layer
