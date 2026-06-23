# Runtime Boundary Rules

`IrisRuntimeService` is a thin transport-independent coordinator.

Do not add observation-kind-specific business logic directly to `IrisRuntimeService`.

Do not add new `isinstance(observation, ...)`, `type(observation) is ...`, or `match observation` routing branches in `IrisRuntimeService`. Put routing in `ObservationRuntimeRouter` or a dedicated runtime handler.

Do not inject concrete activity, presence, occupancy, event-reaction, or future runtime-effect implementations directly into `IrisRuntimeService`. Use typed runtime ports, pipelines, routers, providers, runtimes, policies, gates, or app boundaries.

Runtime responsibilities must remain separated:

- observation integration
- situation context assembly
- observation routing
- event reaction planning
- event reaction presentation
- safety filtering
- cognitive app processing

A new observation effect must choose exactly one extension path:

- `ObservationIntegrationPipeline` for state integration
- `SituationContextProvider` / `WorkspaceContextAssembler` for context snapshots
- `ObservationRuntimeRouter` plus a dedicated runtime handler for runtime-only reactions
- `IrisApp` / `CognitiveCycle` for cognitive response generation

Trusted adapter ingress and unauthenticated external ingress must remain separate.

Do not reuse an integration capability as a reaction, send, emit, or external-effect capability.

Planner, policy, and resolver modules must not construct presentation outputs such as `PresentedOutput` or `AppAction`. They should return decisions, candidates, snapshots, or plans.

Event reaction code must not bypass output safety gates and must not hardcode user-facing response text inside routing or planning code.

Scheduler runner may call `IrisRuntimeService.handle_observation(...)` and may enqueue a `DeliveryEnvelope` only after normal output safety and `DeliverySafetyGate`. Scheduler runner resolves availability through `DeliveryAvailabilityProvider` and passes `AvailabilitySnapshot` into `DeliverySafetyGate`. `IrisRuntimeService` must not return situation context for this path.

`PollAppActions` returns only `LEASED` items. `ReportActionResult` is idempotent for all statuses. Only `FAILED` is retryable; `CANCELLED` and `BLOCKED` are terminal completions. Conflicting repeated reports raise `DeliveryOutboxError`.

`IrisRuntimeService` must not import scheduler or delivery modules, must not branch on scheduler/proactive delivery behavior, and must not enqueue delivery items directly.

`runtime/server.py` may load config, build components, start gRPC, start optional scheduler lifecycle task when `scheduler.enabled`, and cancel tasks on shutdown. It must not contain delivery state transition logic, scheduler decision logic, delivery safety policy, or provider-specific send logic.
