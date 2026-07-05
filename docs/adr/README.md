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
| [0015](0015-local-model-call-budget-and-cascade-policy.md) | Accepted | Local model call budget と cascade policy で user-facing hot path の large LLM 呼び出しを制限する。 |
| [0016](0016-prompt-budget-and-context-compression.md) | Accepted | Prompt section budget と context compression policy で prompt size、trust boundary、overflow を制御する。 |
| [0017](0017-companion-affect-state-model.md) | Accepted | Companion affect state を global mood、relationship、affect trace、space atmosphere、recent tone に分離する。 |
| [0018](0018-appraisal-semantics-split.md) | Accepted | Appraisal を user emotion、Iris への態度、topic sentiment、care intent、dependency-risk hint の typed signal に分離する。 |
| [0019](0019-local-inference-resource-scheduler.md) | Accepted | ローカル推論資源を runtime lease boundary として扱い、user-facing / safety-critical work と background work の競合を deterministic decision で制御する。 |

## 現在の横断方針

- `state.backend = "sqlite"` は account、memory、relationship、affect、activity journal、delivery outbox、scheduler target store、safety audit journal、runtime learning background job queue、memory candidate review store を durable にする。Transcript は `conversation.transcript.enabled = true` の場合だけ durable にする。
- activity projection、presence、space occupancy、ephemeral space bindings、short-term conversation history、learning dispatch は process-local。
- ADR 0005 は欠番を埋めるため新規追加した。既存 ADR 0008 は diagnostics / observability の決定であり、LLM provider runtime policy の置き場としては広すぎる。
- ADR 0014 は重複していた public remote auth boundary の ADR 番号を末尾へ移動したもの。既存 0010〜0013 の番号は保持する。ADR 0015 は後続の model call budget / cascade policy。
- ADR 0016 は #91 の prompt budget / context compression policy の source of truth であり、#94 / #98 / #78 の prompt integration gate になる。
- ADR 0017 は #104 の companion affect state boundary を固定し、#100 / #102 / #72 が参照する state vocabulary を提供する。
- ADR 0018 は #100 の appraisal semantics split を固定し、#102 / #72 / #82 が raw valence ではなく typed signal を参照できる境界を提供する。
- ADR 0019 は #93 の local inference resource scheduler boundary を固定し、#78 / #69 / #70 / #72 が local inference resource policy を参照できる境界を提供する。
