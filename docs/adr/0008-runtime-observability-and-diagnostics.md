# ADR 0008: Runtime Observability and Diagnostics

## Status

Accepted

## Context

Iris は長時間動く Cognitive Runtime であり、1 request の流れ、LLM 呼び出し、起動前後の provider readiness を安全に追跡できる必要がある。一方で、初期実装から外部監視 stack を入れると event model が固まる前に依存と運用負荷が増える。

## Decision

Runtime の可観測性は `iris/runtime/observability/` に置く。runtime business code は `RuntimeLogger`、`RuntimeObservationObserver`、`RuntimeLLMRequestObserver` の typed boundary に依存し、Loguru への直接依存を広げない。

`IrisRuntimeService` は observability boundary API に依存してよい。具体例は `RuntimeTraceContext`、`bind_trace_context`、`trace_extra` を置く `iris.runtime.observability.context` と、`RuntimeObservationObserver` を置く `iris.runtime.observability.ports`。一方で `LoguruRuntimeLogger`、`LoggingRuntimeObservationObserver`、`RuntimeLLMRequestObserver`、startup diagnostics runner、exporter/backend 実装、provider-specific diagnostics などの concrete observability implementation には依存しない。

この境界により、service は typed port / context 経由で観測し、server / wiring が concrete observer を設置する。observability implementation は routing、retry、safety、delivery、memory behavior を決めない。

`context.py` と `ports.py` は意図的に pure boundary module として保つ。これにより `IrisRuntimeService` は concrete observability implementation へ indirect dependency を持たずに依存できる。

`correlation_id` を primary trace key とする。`ObservationEnvelope.correlation_id` がある場合はそれを使い、ない場合は `observation_id` を trace fallback として使う。trace context は `contextvars` で request scope に束縛する。

ログに出してよいものは安全な ID と metadata に限定する。例:

- `correlation_id`
- `observation_id`
- `observation_kind`
- `ingress_kind`
- `adapter_id`
- `provider`
- `actor_id`
- `space_id`
- `route`
- `latency_ms`
- `model`
- `finish_reason`
- `error_type`

ログに出してはいけないもの:

- user text
- prompt text
- memory content
- raw provider response
- system instruction
- API key
- token
- secret

Sensitive field filtering は broad substring match ではなく exact key と sensitive suffix のみで行う。`memory_result_count`、`context_assembled`、`content_type` のような safe diagnostic field は保持する。

Runtime は当面 Loguru-based structured logging を使う。`configure_runtime_logging` は既存の backend 設定を維持し、`LoguruRuntimeLogger` はその上に置く facade とする。

LLM request logs は runtime trace context aware にする。runtime wiring が作る LLM client は `RuntimeLLMRequestObserver` で wrap し、adapter-level の `LoggingRequestObserver` は低レベル利用と既存 adapter tests のために残す。

`iris.runtime.doctor` は read-only / non-mutating command とする。設定 discovery、設定 validation、state backend、SQLite/log path permission、server、model slots、startup diagnostics readiness、delivery/scheduler enablement を確認する。`diagnostics.warmup_models = true` の設定でも provider warmup は実行しない。

OpenTelemetry、Prometheus、Sentry、structlog、Rich、外部 exporter は deferred。internal event model と safe field policy が安定してから導入を再検討する。初期実装では新規 dependency を追加しない。

## Consequences

Runtime request lifecycle と LLM request lifecycle は同じ `correlation_id` で追跡できる。外部 monitoring backend がなくても local log と runtime doctor で初期切り分けができる。

Component-level hooks は event boundary を増やす作業になるため、Phase 6 以降の小さな差分で追加する。観測 code は routing、retry、safety、delivery、memory の判断を行わない。
