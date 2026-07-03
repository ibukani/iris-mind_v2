# Iris ADR

Architecture Decision Record の一覧。新規 ADR は次の見出しを使う。

```text
Status
Context
Decision
Non-decisions
Consequences
Implementation anchors
```

## Index

| ADR | Status | Decision |
|---|---|---|
| [0001](0001-ephemeral-deterministic-space.md) | Accepted | Default runtime は `provider + provider_space_ref` から Space を ephemeral deterministic に解決する。 |
| [0002](0002-runtime-state-persistence-policy.md) | Accepted | `state.backend` は durable companion state と audit history の範囲だけを決める。 |
| [0003](0003-identity-owned-memory.md) | Accepted | Memory の主 scope は `ActorId`、`space_id` は context scope。 |
| [0004](0004-relationship-and-affect-state.md) | Accepted | Relationship / affect は memory ではなく専用 store の current state。 |
| [0005](0005-llm-provider-runtime-policy.md) | Accepted | LLM provider は typed config と adapter 境界で扱い、runtime wiring が注入する。 |
| [0006](0006-proactive-scheduler-delivery-safety.md) | Accepted | Scheduler は typed observation を発行し、配送は safety と outbox を通す。 |
| [0007](0007-runtime-boundary-guard.md) | Accepted | `IrisRuntimeService` を薄い coordinator に保ち、境界を architecture tests で守る。 |
| [0008](0008-runtime-observability-and-diagnostics.md) | Accepted | Runtime observability は typed boundary API と safe metadata に限定する。 |
| [0009](0009-feature-presentation-runtime-boundaries.md) | Accepted | Feature、Presentation、Runtime の責務を分離し、features が runtime / presentation を吸収しないようにする。 |
| [0010](0010-runtime-learning-delivery-history-boundary.md) | Accepted | Delivery result 後に learning/history を確定し、generated output と delivered output を分離する。 |
| [0011](0011-memory-vector-index-backend.md) | Accepted | Vector index は memory record の正本ではなく derived retrieval backend として扱う。 |
| [0012](0012-sqlite-schema-migration-backup-recovery.md) | Accepted | SQLite backend は明示的な schema migration、backup、recovery policy で運用する。 |
| [0013](0013-local-llm-lifecycle-readiness-warmup.md) | Accepted | Local LLM lifecycle / readiness / warmup を provider-neutral state と request-time probe で扱う。 |
| [0014](0014-public-remote-auth-boundary.md) | Accepted | Runtime auth は RemoteAuthBoundary を介して provider payload から context を検証する。 |

## 現在の横断方針

- `state.backend = "sqlite"` は account、memory、relationship、affect、activity journal、delivery outbox、scheduler target store、safety audit journal、runtime learning background job queue、memory candidate review store を durable にする。Transcript は `conversation.transcript.enabled = true` の場合だけ durable にする。
- activity projection、presence、space occupancy、ephemeral space bindings、short-term conversation history、learning dispatch は process-local。
- ADR 0005 は欠番を埋めるため新規追加した。既存 ADR 0008 は diagnostics / observability の決定であり、LLM provider runtime policy の置き場としては広すぎる。
- ADR 0014 は重複していた public remote auth boundary の ADR 番号を末尾へ移動したもの。既存 0010〜0013 の番号は保持する。
