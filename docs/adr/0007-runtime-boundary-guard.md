# ADR 0007: Runtime Boundary Guard

## Status

Accepted.

## Context

Iris の runtime は transport、scheduler、delivery、ingress をつなぐ境界であり、認知・presentation・safety・外部送信の責務を吸収してはならない。特に `IrisRuntimeService` は便利な中心サービスに肥大化しやすいため、境界方針を architecture tests で実行可能にする。

## Decision

`IrisRuntimeService` は薄い transport-independent coordinator に限定する。観測 state integration、situation context assembly、observation routing、event reaction handler、`IrisApp` 委譲をつなぐだけにする。

Concrete `Observation` routing は `iris/runtime/observation_router.py` に集約する。`IrisRuntimeService` や runner/planner/resolver は concrete `Observation` subclass の `isinstance` / `type` / `match` branch を持たない。

External client ingress と trusted adapter ingress は分離する。public gRPC `SubmitObservation` の default は unauthenticated external client であり、capability は空にする。trusted adapter mode は明示 profile と明示 capability を要求する。trusted path だけが必要に応じて delivery route hint を保持する。

`IrisRuntimeService` は delivery enqueue、scheduler 呼び出し、外部 SDK 呼び出し、user-facing text construction、`AppAction` construction を行わない。`PresentedOutput(text=None)` による no-send だけを直接構築してよい。

Event reaction は trust policy と situation context を満たす場合だけ runner を呼び、sendable output は必ず `OutputSafetyGate` を通す。`BLOCK` は `PresentedOutput(text=None)` へ落とす。`ALLOW` は reaction output を返す。

Scheduler は typed internal `Observation` を `IrisRuntimeService` に渡す。enqueue は通常の cognitive / action safety / presentation / output safety path と `DeliverySafetyGate` を通った後だけ許可する。scheduler は LLM adapter、presenter、gRPC server、外部 SDK を import しない。

`DeliveryOutbox` は pull-based outbox であり sender ではない。`DeliveryOutbox` と実装は `IrisRuntimeService`、`IrisApp`、`CognitiveCycle`、Presenter、外部 SDK に依存しない。外部 client が poll し、送信結果を report する。

gRPC server は `IrisRuntimeService` と `AppActionBroker` protocol に委譲する。concrete `DeliveryOutbox` や `SchedulerRunner` に依存しない。

## Executable Guards

- `tests/architecture/test_runtime_boundary_guards.py`
- `tests/architecture/test_runtime_service_shape.py`
- `tests/architecture/test_coordinator_type_branching.py`
- `tests/runtime/test_observation_envelope_ingress.py`
- `tests/adapters/grpc/test_grpc_ingress_profiles.py`
- `tests/runtime/test_activity_event_reaction_boundary.py`
- `tests/runtime/test_scheduler_delivery_boundary.py`

## Consequences

runtime に新しい副作用を追加する場合、`IrisRuntimeService` へ直接足さず、router、ingress handler、scheduler runner、delivery outbox、または adapter mapper の境界に置く。新しい例外 allowlist は file path、exact import/construct、理由、削除条件を持つ必要がある。
