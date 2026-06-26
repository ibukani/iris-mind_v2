# Architecture Review Checklist

Use this checklist for changes that touch runtime, cognitive flow, observations, memory, config, safety, presentation, adapters, or feature boundaries.

## 1. Layer Boundaries

- [ ] `contracts/` does not import `runtime/`, `cognitive/`, `adapters/`, or `features/`.
- [ ] `cognitive/` does not import `runtime/`, `adapters/`, or `features/`.
- [ ] `features/` does not import `runtime/` or `adapters/`.
- [ ] Adapter-specific concerns stay in `adapters/`.
- [ ] Generated/protobuf details do not leak into contracts, cognitive, or runtime domain logic.

## 2. Runtime Boundary

- [ ] `IrisRuntimeService` remains a thin coordinator.
- [ ] No new concrete observation-type routing was added to `IrisRuntimeService`.
- [ ] New runtime behavior uses a dedicated router, pipeline, provider, runtime handler, or app/cognitive boundary.
- [ ] Runtime integration, context assembly, routing, reaction, presentation, safety, and cognitive processing remain separate.
- [ ] No low-level integrator/store/journal/resolver/planner/runner was injected directly into `IrisRuntimeService`.
- [ ] `IrisRuntimeService` does not import scheduler, delivery, adapters, presentation, safety, or external SDK modules.
- [ ] Concrete `Observation` routing lives in `iris/runtime/observation_router.py`, not service/runner/planner code.
- [ ] Public gRPC `SubmitObservation` defaults to external-client ingress; trusted adapter ingress requires explicit capabilities.
- [ ] `IrisRuntimeService` does not enqueue delivery, call scheduler, construct user-facing text, or construct `AppAction`.
- [ ] Scheduler enqueues only after normal output path and `DeliverySafetyGate`; delivery outbox remains pull-based and never sends.

## 3. Observation and Routing

- [ ] New observation types have typed contracts.
- [ ] Observation routing does not rely on stringly typed `kind`/`type` branches in coordinators.
- [ ] Concrete observation handling is isolated to dedicated routers or handlers.
- [ ] No adapter-specific observation assumptions leak into cognitive or contracts.

## 4. Trust and Capability

- [ ] External client ingress and trusted adapter ingress remain distinct.
- [ ] Each side effect has an explicit capability.
- [ ] Integration capability is not reused for reaction/send/emit behavior.
- [ ] No unauthenticated external observation can update trusted runtime state.
- [ ] No unauthenticated external observation can trigger an external send or event reaction.

## 5. Cognitive Cycle and Workspace

- [ ] `CognitiveCycle` remains a pipeline coordinator, not a God Service.
- [ ] `PipelineStep` implementations return typed result objects.
- [ ] Pipeline steps do not return raw dicts, lists, tuples, `None`, or `WorkspaceFrame`.
- [ ] `WorkspaceFrame` is not mutated directly.
- [ ] Frame updates go through approved builder/replacement mechanisms.

## 6. Safety and Presentation

- [ ] User-facing output goes through the presenter/output boundary.
- [ ] External app actions go through safety gates.
- [ ] Planner, policy, resolver, and routing modules do not construct `PresentedOutput` or `AppAction`.
- [ ] Event reactions do not bypass `OutputSafetyGate`.
- [ ] No external send is introduced without explicit safety semantics.

## 7. Memory

- [ ] `MutableMemoryStore` remains the canonical memory record lifecycle owner.
- [ ] Vector indexes index memory ids or index entries; they do not become second memory stores.
- [ ] Memory retrieval resolves records through the canonical memory store.
- [ ] Memory extraction and persistence behavior are explicit and tested.
- [ ] Raw logs, memory records, and derived memories remain conceptually separate.

## 8. Config and Schema

- [ ] Runtime config defaults and config specs remain consistent.
- [ ] New config fields are represented in editable config specs unless explicitly excluded.
- [ ] Config env names and CLI flags are unique.
- [ ] Control Plane-facing schema/config metadata remains accurate.
- [ ] No duplicated default source is introduced without a consistency test.

## 9. Typing and Boundaries

- [ ] Internal boundaries do not use `dict[str, Any]`, `dict[str, object]`, or equivalent untyped mappings.
- [ ] External uncertainty is contained in adapters.
- [ ] Protocols and dataclasses are used for internal contracts.
- [ ] New public APIs are typed and tested.
- [ ] No temporary compatibility shim is added without removal criteria and tests.

## 10. Async and Side Effects

- [ ] No blocking I/O is introduced inside `async def`.
- [ ] Sync I/O in async flows is offloaded with `asyncio.to_thread` or equivalent.
- [ ] No global mutable registry or service locator is introduced.
- [ ] No silent broad exception swallowing is introduced.
- [ ] Side effects are explicit and placed behind ports/adapters where appropriate.

## 11. Product/Future Compatibility

- [ ] The change works for Discord, CLI, and future app adapters without adapter-specific leakage.
- [ ] The change does not make proactive behavior harder to add later.
- [ ] The change does not confuse ephemeral runtime state with durable memory.
- [ ] The change preserves Iris as a cognitive companion runtime, not a generic chatbot wrapper.
- [ ] The abstraction is neither obviously under-factored nor over-factored.

## 12. Verification

- [ ] `make static-arch` passes if available.
- [ ] `make quick` passes.
- [ ] Targeted behavior tests were added or updated.
- [ ] Architecture tests were added or updated when a new architectural rule was introduced.
- [ ] Residual risks are documented in the final report.
